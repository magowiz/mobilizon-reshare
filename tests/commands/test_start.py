import uuid
from logging import DEBUG

import pytest

import mobilizon_reshare.publishers.platforms.platform_mapping
from mobilizon_reshare.event.event import MobilizonEvent, EventPublicationStatus
from mobilizon_reshare.main.start import start
from mobilizon_reshare.models import event
from mobilizon_reshare.models.event import Event
from mobilizon_reshare.models.publication import PublicationStatus
from mobilizon_reshare.models.publisher import Publisher


def simple_event_element():

    return {
        "beginsOn": "2021-05-23T12:15:00Z",
        "description": "Some description",
        "endsOn": "2021-05-23T15:15:00Z",
        "onlineAddress": None,
        "options": {"showEndTime": True, "showStartTime": True},
        "physicalAddress": None,
        "picture": None,
        "title": "test event",
        "url": "https://some_mobilizon/events/1e2e5943-4a5c-497a-b65d-90457b715d7b",
        "uuid": str(uuid.uuid4()),
    }


@pytest.fixture
def mobilizon_answer(elements):
    return {"data": {"group": {"organizedEvents": {"elements": elements}}}}


@pytest.fixture
async def mock_publisher_config(
    monkeypatch, mock_publisher_class, mock_formatter_class
):
    p = Publisher(name="test")
    await p.save()

    p2 = Publisher(name="test2")
    await p2.save()

    def _mock_active_pub():
        return ["test", "test2"]

    def _mock_pub_class(name):
        return mock_publisher_class

    def _mock_format_class(name):
        return mock_formatter_class

    monkeypatch.setattr(event, "get_active_publishers", _mock_active_pub)
    monkeypatch.setattr(
        mobilizon_reshare.publishers.platforms.platform_mapping,
        "get_publisher_class",
        _mock_pub_class,
    )
    monkeypatch.setattr(
        mobilizon_reshare.publishers.platforms.platform_mapping,
        "get_formatter_class",
        _mock_format_class,
    )
    return p


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "elements", [[]],
)
async def test_start_no_event(
    mock_mobilizon_success_answer, mobilizon_answer, caplog, elements
):

    with caplog.at_level(DEBUG):
        assert await start() is None
        assert "No event to publish found" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "elements",
    [[simple_event_element()], [simple_event_element(), simple_event_element()]],
)
@pytest.mark.parametrize("publication_window", [(0, 24)])
async def test_start_new_event(
    mock_mobilizon_success_answer,
    mobilizon_answer,
    caplog,
    mock_publisher_config,
    mock_publication_window,
    message_collector,
):

    with caplog.at_level(DEBUG):
        # calling the start command
        assert await start() is None

        # since the mobilizon_answer contains at least one result, one event to publish must be found and published
        # by the publisher coordinator
        assert "Event to publish found" in caplog.text
        assert message_collector == [
            "test event|Some description",
            "test event|Some description",
        ]

        all_events = (
            await Event.all()
            .prefetch_related("publications")
            .prefetch_related("publications__publisher")
        )

        # the start command should save all the events in the database
        assert len(all_events) == len(
            mobilizon_answer["data"]["group"]["organizedEvents"]["elements"]
        ), all_events

        # it should create a publication for each publisher
        publications = all_events[0].publications
        assert len(publications) == 2, publications

        # all the other events should have no publication
        for e in all_events[1:]:
            assert len(e.publications) == 0, e.publications

        # all the publications for the first event should be saved as COMPLETED
        for p in publications[1:]:
            assert p.status == PublicationStatus.COMPLETED

        # the derived status for the event should be COMPLETED
        assert (
            MobilizonEvent.from_model(all_events[0]).status
            == EventPublicationStatus.COMPLETED
        )