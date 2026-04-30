def register_blueprints(app, scheduler):
    from apis.rules_api import rules_bp
    from apis.cron_api import cron_bp
    from apis.tasks_api import tasks_bp
    from apis.logs_api import logs_bp
    from apis.data_api import data_bp

    app.register_blueprint(rules_bp, url_prefix="/api/rules")
    app.register_blueprint(cron_bp, url_prefix="/api/cron")
    app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")
    app.register_blueprint(data_bp, url_prefix="/api/data")
