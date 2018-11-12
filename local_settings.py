import os
env = {
    'LISTEN_PORT': 8000,
    'LISTEN_HOST': "0.0.0.0",
    # Redis
    'REDIS_HOST': 'localhost',
    'REDIS_PORT': '6379',
    'REDIS_DB': 0,
    # Celery
    'CELERY_BROKER': 'redis://localhost:6379/3',
    'CELERY_BACKEND': 'redis://localhost:6379/3',
    'CELERY_TASK_RESULT_EXPIRES': 1440,
    'CELERY_DEFAULT_QUEUE': 'slack_requests',
    'DEFAULT_SLACK_CHANNEL': 'email',
}
