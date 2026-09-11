from django.core.management.base import BaseCommand

from panel.maintenance import run_job


class Command(BaseCommand):
    help = 'Run one maintenance job requested by a panel superuser.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('job_id')

    def handle(self, *args, **options):
        run_job(options['job_id'])
