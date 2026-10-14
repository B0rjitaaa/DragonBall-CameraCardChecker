from django.apps import AppConfig


class ScansConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "scans"
    verbose_name = "Escaneos"

    def ready(self):
        from celery.signals import worker_ready

        @worker_ready.connect(weak=False)
        def warm_up(**_kwargs):
            from .services import warm_up

            warm_up()
