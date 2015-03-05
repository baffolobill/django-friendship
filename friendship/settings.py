from django.conf import settings

# use django-notification if installed
USE_NOTIFICATION_APP = getattr(
    settings,
   'FRIENDSHIP_USE_NOTIFICATION_APP',
    True)

NOTIFY_ABOUT_NEW_FRIENDS_OF_FRIEND = getattr(
    settings,
    'NOTIFY_ABOUT_NEW_FRIENDS_OF_FRIEND',
     False)

NOTIFY_ABOUT_FRIENDS_REMOVAL = getattr(
    settings,
    'NOTIFY_ABOUT_FRIENDS_REMOVAL',
    False)
