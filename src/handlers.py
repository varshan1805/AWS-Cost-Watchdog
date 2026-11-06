"""
Lambda entry points. Terraform points the functions at these:
    handlers.scan       -> daily waste scan
    handlers.schedule   -> start/stop tagged instances
"""

from watchdog import scanner, scheduler


def scan(event, context):
    return scanner.handler(event, context)


def schedule(event, context):
    return scheduler.handler(event, context)
