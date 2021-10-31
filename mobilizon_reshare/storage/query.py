import logging
import sys
from typing import Iterable, Optional, Dict, List
from uuid import UUID

import arrow
from arrow import Arrow
from tortoise.queryset import QuerySet
from tortoise.transactions import atomic

from mobilizon_reshare.event.event import MobilizonEvent, EventPublicationStatus
from mobilizon_reshare.models.event import Event
from mobilizon_reshare.models.publication import Publication, PublicationStatus
from mobilizon_reshare.models.publisher import Publisher
from mobilizon_reshare.publishers import get_active_publishers
from mobilizon_reshare.publishers.coordinator import PublisherCoordinatorReport

logger = logging.getLogger(__name__)

# This is due to Tortoise community fixtures to
# set up and tear down a DB instance for Pytest.
# See: https://github.com/tortoise/tortoise-orm/issues/419#issuecomment-696991745
# and: https://docs.pytest.org/en/stable/example/simple.html

CONNECTION_NAME = "models" if "pytest" in sys.modules else None


async def prefetch_event_relations(queryset: QuerySet[Event]) -> list[Event]:
    return (
        await queryset.prefetch_related("publications__publisher")
        .order_by("begin_datetime")
        .distinct()
    )


def _add_date_window(
    query,
    field_name: str,
    from_date: Optional[Arrow] = None,
    to_date: Optional[Arrow] = None,
):
    if from_date:
        query = query.filter(**{f"{field_name}__gt": from_date.to("utc").datetime})
    if to_date:
        query = query.filter(**{f"{field_name}__lt": to_date.to("utc").datetime})
    return query


@atomic(CONNECTION_NAME)
async def publications_with_status(
    status: PublicationStatus,
    event_mobilizon_id: Optional[UUID] = None,
    from_date: Optional[Arrow] = None,
    to_date: Optional[Arrow] = None,
) -> Dict[UUID, Publication]:
    query = Publication.filter(status=status)

    if event_mobilizon_id:
        query = query.prefetch_related("event").filter(
            event__mobilizon_id=event_mobilizon_id
        )

    query = _add_date_window(query, "timestamp", from_date, to_date)

    publications_list = (
        await query.prefetch_related("publisher").order_by("timestamp").distinct()
    )
    return {pub.id: pub for pub in publications_list}


async def events_without_publications(
    from_date: Optional[Arrow] = None, to_date: Optional[Arrow] = None,
) -> Iterable[MobilizonEvent]:
    query = Event.filter(publications__id=None)

    return map(
        MobilizonEvent.from_model,
        await prefetch_event_relations(
            _add_date_window(query, "begin_datetime", from_date, to_date)
        ),
    )


async def events_with_status(
    status: list[EventPublicationStatus],
    from_date: Optional[Arrow] = None,
    to_date: Optional[Arrow] = None,
) -> Iterable[MobilizonEvent]:
    def _filter_event_with_status(event: Event) -> bool:
        # This computes the status client-side instead of running in the DB. It shouldn't pose a performance problem
        # in the short term, but should be moved to the query if possible.
        event_status = MobilizonEvent.compute_status(list(event.publications))
        return event_status in status

    query = Event.all()

    return map(
        MobilizonEvent.from_model,
        filter(
            _filter_event_with_status,
            await prefetch_event_relations(
                _add_date_window(query, "begin_datetime", from_date, to_date)
            ),
        ),
    )


async def get_all_events(
    from_date: Optional[Arrow] = None, to_date: Optional[Arrow] = None,
) -> Iterable[MobilizonEvent]:
    return map(
        MobilizonEvent.from_model,
        await prefetch_event_relations(
            _add_date_window(Event.all(), "begin_datetime", from_date, to_date)
        ),
    )


async def get_published_events(
    from_date: Optional[Arrow] = None, to_date: Optional[Arrow] = None
) -> Iterable[MobilizonEvent]:
    """
    Retrieves events that are not waiting. Function could be renamed to something more fitting
    :return:
    """
    return await events_with_status(
        [
            EventPublicationStatus.COMPLETED,
            EventPublicationStatus.PARTIAL,
            EventPublicationStatus.FAILED,
        ],
        from_date=from_date,
        to_date=to_date,
    )


async def get_mobilizon_event_publications(
    event: MobilizonEvent,
) -> Iterable[Publication]:
    models = await prefetch_event_relations(
        Event.filter(mobilizon_id=event.mobilizon_id)
    )
    return models[0].publications


async def get_publisher_by_name(name: str) -> Publisher:
    return await Publisher.filter(name=name).first()


async def save_event(event: MobilizonEvent) -> Event:
    event_model = event.to_model()
    await event_model.save()
    return event_model


async def create_publisher(name: str, account_ref: Optional[str] = None) -> None:
    await Publisher.create(name=name, account_ref=account_ref)


@atomic(CONNECTION_NAME)
async def update_publishers(names: Iterable[str],) -> None:
    names = set(names)
    known_publisher_names = set(p.name for p in await Publisher.all())
    for name in names.difference(known_publisher_names):
        logging.info(f"Creating {name} publisher")
        await create_publisher(name)


async def publication_with_publisher_name(
    publisher_name: str, event_model: Event, status: PublicationStatus
) -> Publication:
    publisher = await get_publisher_by_name(publisher_name)
    return Publication(
        status=status,
        event_id=event_model.id,
        publisher_id=publisher.id,
        publisher=publisher,
    )


@atomic(CONNECTION_NAME)
async def save_publication(
    publisher_name: str, event_model: Event, status: PublicationStatus
) -> Publication:
    publication = await publication_with_publisher_name(
        publisher_name, event_model, status
    )
    await publication.save()
    return publication


@atomic(CONNECTION_NAME)
async def create_event_publication_models(event: MobilizonEvent) -> list[Publication]:
    publishers = get_active_publishers()
    event_model = (
        await prefetch_event_relations(Event.filter(mobilizon_id=event.mobilizon_id))
    )[0]
    result = []
    for publisher in publishers:
        result.append(
            await publication_with_publisher_name(
                publisher, event_model, PublicationStatus.UNSAVED
            )
        )
    return result


@atomic(CONNECTION_NAME)
async def create_unpublished_events(
    unpublished_mobilizon_events: Iterable[MobilizonEvent],
) -> List[MobilizonEvent]:
    # We store only new events, i.e. events whose mobilizon_id wasn't found in the DB.
    unpublished_event_models: set[UUID] = set(
        map(lambda event: event.mobilizon_id, await events_without_publications())
    )
    unpublished_events = list(
        filter(
            lambda event: event.mobilizon_id not in unpublished_event_models,
            unpublished_mobilizon_events,
        )
    )

    for event in unpublished_events:
        await save_event(event)

    return unpublished_events


@atomic(CONNECTION_NAME)
async def save_publication_report(
    coordinator_report: PublisherCoordinatorReport, publications: List[Publication],
) -> None:
    publications = {m.id: m for m in publications}
    for publication_report in coordinator_report.reports:
        publication_id = publication_report.publication.id
        publications[publication_id].status = publication_report.status
        publications[publication_id].reason = publication_report.reason
        publications[publication_id].timestamp = arrow.now().datetime

        await publications[publication_id].save()
