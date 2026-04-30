def register_blueprints(app, scheduler):
    from APP.dashboard.apis.rules_api import rules_bp
    from APP.dashboard.apis.cron_api import cron_bp, set_scheduler
    from APP.dashboard.apis.tasks_api import tasks_bp
    from APP.dashboard.apis.logs_api import logs_bp
    from APP.dashboard.apis.data_api import data_bp

    # Inject scheduler into cron_api before any requests arrive
    set_scheduler(scheduler)

    app.register_blueprint(rules_bp, url_prefix="/api/rules")
    app.register_blueprint(cron_bp, url_prefix="/api/cron")
    app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")
    app.register_blueprint(data_bp, url_prefix="/api/data")
