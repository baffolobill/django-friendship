try:
    from hsiow.compat import get_user_model
except ImportError:
    try:
        from mongoengine.django.mongo_auth.models import get_user_document as get_user_model
    except ImportError:
        from mongoengine.django.auth import User
        get_user_model = lambda: User
