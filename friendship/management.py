from django.conf import settings
from django.utils.translation import ugettext_noop as _

from mongoengine import signals
from friendship import settings as friends_settings


if friends_settings.USE_NOTIFICATION_APP and "notification" in settings.INSTALLED_APPS:
    from notification import models as notification

    def create_notice_types(app, created_models, verbosity, **kwargs):
        notification.create_notice_type(
            "friendship_request",
            _("Invitation received"),
            _("You have received an invitation."),
            default=1)

        notification.create_notice_type(
            "friendship_request_sent",
            _("Invitation sent"),
            _("You have sent an invitation."),
            default=1)

        notification.create_notice_type(
            "friendship_accept",
            _("Acceptance received"),
            _("An invitation you sent has been accepted."),
            default=1)

        notification.create_notice_type(
            "friendship_accept_sent",
            _("Acceptance sent"),
            _("You have accepted an invitation you received."),
            default=1)

        if friends_settings.NOTIFY_ABOUT_NEW_FRIENDS_OF_FRIEND:
            notification.create_notice_type(
                "friendship_otherconnect",
                _("Other connection"),
                _("One of your friends has a new friend."),
                default=1)

        if friends_settings.NOTIFY_ABOUT_FRIENDS_REMOVAL:
            notification.create_notice_type(
                "friendship_friend_removed",
                _("Friend removed"),
                _("One person was removed from your friends."),
                default=1)

    signals.post_init.connect(create_notice_types, sender=notification)
else:
    print "Skipping creation of NoticeTypes as notification app not found"
