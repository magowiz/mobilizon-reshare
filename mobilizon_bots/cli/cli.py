import functools

import click
from arrow import Arrow
from click import pass_context, pass_obj

from mobilizon_bots.cli import safe_execution
from mobilizon_bots.cli.inspect_event import inspect_events
from mobilizon_bots.cli.main import main
from mobilizon_bots.event.event import EventPublicationStatus

settings_file_option = click.option("--settings-file", type=click.Path(exists=True))
from_date_option = click.option(
    "--begin",
    type=click.DateTime(),
    expose_value=True,
    help="Include only events that begin after this datetime",
)
to_date_option = click.option(
    "--end",
    type=click.DateTime(),
    expose_value=True,
    help="Include only events that begin before this datetime",
)


@click.group()
def mobilizon_bots():
    pass


@mobilizon_bots.command()
@settings_file_option
def start(settings_file):
    safe_execution(main, settings_file=settings_file)


@mobilizon_bots.group()
@from_date_option
@to_date_option
@pass_context
def inspect(ctx, begin, end):
    ctx.ensure_object(dict)
    ctx.obj["begin"] = Arrow.fromdatetime(begin) if begin else None
    ctx.obj["end"] = Arrow.fromdatetime(end) if end else None
    pass


@inspect.command()
@settings_file_option
@pass_obj
def all(obj, settings_file):
    safe_execution(
        functools.partial(inspect_events, frm=obj["begin"], to=obj["end"],),
        settings_file,
    )


@inspect.command()
@pass_obj
@settings_file_option
def waiting(obj, settings_file):
    safe_execution(
        functools.partial(
            inspect_events,
            EventPublicationStatus.WAITING,
            frm=obj["begin"],
            to=obj["end"],
        ),
        settings_file,
    )


@inspect.command()
@pass_obj
@settings_file_option
def failed(obj, settings_file):
    safe_execution(
        functools.partial(
            inspect_events,
            EventPublicationStatus.FAILED,
            frm=obj["begin"],
            to=obj["end"],
        ),
        settings_file,
    )


@inspect.command()
@pass_obj
@settings_file_option
def partial(obj, settings_file):
    safe_execution(
        functools.partial(
            inspect_events,
            EventPublicationStatus.PARTIAL,
            frm=obj["begin"],
            to=obj["end"],
        ),
        settings_file,
    )


@inspect.command()
@settings_file_option
@pass_obj
def completed(obj, settings_file):
    safe_execution(
        functools.partial(
            inspect_events,
            EventPublicationStatus.COMPLETED,
            frm=obj["begin"],
            to=obj["end"],
        ),
        settings_file,
    )


if __name__ == "__main__":
    mobilizon_bots()