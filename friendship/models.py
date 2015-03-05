from __future__ import unicode_literals

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from mongoengine import fields, signals, Document
from mongoengine.queryset import Q, QuerySet

from friendship.settings import (USE_NOTIFICATION_APP,
    NOTIFY_ABOUT_NEW_FRIENDS_OF_FRIEND, NOTIFY_ABOUT_FRIENDS_REMOVAL)
from friendship.compat import get_user_model
from friendship.exceptions import AlreadyExistsError
from friendship.signals import (friendship_request_created, \
    friendship_request_rejected, friendship_request_canceled, \
    friendship_request_viewed, friendship_request_accepted, \
    friendship_removed, inspirations_created, inspirationals_created,
    inspirations_removed, inspirationals_removed, blocking_created,
    blocking_removed)



CACHE_TYPES = {
    'friends': 'f-%s',
    'inspirations': 'ifo-%s',
    'inspirationals': 'ifl-%s',
    'requests': 'fr-%s',
    'sent_requests': 'sfr-%s',
    'unread_requests': 'fru-%s',
    'unread_request_count': 'fruc-%s',
    'read_requests': 'frr-%s',
    'rejected_requests': 'frj-%s',
    'unrejected_requests': 'frur-%s',
    'unrejected_request_count': 'frurc-%s',
    'blocked': 'bl-%s',
}

BUST_CACHES = {
    'friends': ['friends'],
    'inspirations': ['inspirations'],
    'inspirationals': ['inspirationals'],
    'requests': [
        'requests',
        'unread_requests',
        'unread_request_count',
        'read_requests',
        'rejected_requests',
        'unrejected_requests',
        'unrejected_request_count',
    ],
    'sent_requests': ['sent_requests'],
    'blocked': ['blocked'],
}


def cache_key(kind, user_pk):
    """
    Build the cache key for a particular kind of cached value
    """
    return CACHE_TYPES[kind] % user_pk


def bust_cache(kind, user_pk):
    """
    Bust our cache for a given kind, can bust multiple caches
    """
    bust_keys = BUST_CACHES[kind]
    keys = [CACHE_TYPES[k] % user_pk for k in bust_keys]
    cache.delete_many(keys)


@python_2_unicode_compatible
class FriendshipRequest(Document):
    """ Model to represent friendship requests """
    from_user = fields.ReferenceField(get_user_model())
    to_user = fields.ReferenceField(get_user_model(), unique_with=['from_user'])

    message = fields.StringField(
        verbose_name=_('Message'),
        max_length=1000,
        required=False)

    created = fields.DateTimeField(default=timezone.now, null=True)
    rejected = fields.DateTimeField(required=False, null=True)
    viewed = fields.DateTimeField(required=False, null=True)

    class Meta:
        verbose_name = _('Friendship Request')
        verbose_name_plural = _('Friendship Requests')

    def __str__(self):
        return "User #%s friendship requested #%s" % (self.from_user.pk, self.to_user.pk)

    def accept(self):
        """ Accept this friendship request """
        relation1 = Friend.objects.create(
            from_user=self.from_user,
            to_user=self.to_user
        )

        relation2 = Friend.objects.create(
            from_user=self.to_user,
            to_user=self.from_user
        )

        friendship_request_accepted.send(
            sender=self,
            from_user=self.from_user,
            to_user=self.to_user
        )

        self.delete()

        # Delete any reverse requests
        FriendshipRequest.objects.filter(
            from_user=self.to_user,
            to_user=self.from_user
        ).delete()

        # Bust requests cache - request is deleted
        bust_cache('requests', self.to_user.pk)
        bust_cache('sent_requests', self.from_user.pk)
        # Bust reverse requests cache - reverse request might be deleted
        bust_cache('requests', self.from_user.pk)
        bust_cache('sent_requests', self.to_user.pk)
        # Bust friends cache - new friends added
        bust_cache('friends', self.to_user.pk)
        bust_cache('friends', self.from_user.pk)

        return True

    def reject(self):
        """ reject this friendship request """
        self.rejected = timezone.now()
        self.save()
        friendship_request_rejected.send(sender=self)
        bust_cache('requests', self.to_user.pk)

    def cancel(self):
        """ cancel this friendship request """
        self.delete()
        friendship_request_canceled.send(sender=self)
        bust_cache('requests', self.to_user.pk)
        bust_cache('sent_requests', self.from_user.pk)
        return True

    def mark_viewed(self):
        self.viewed = timezone.now()
        friendship_request_viewed.send(sender=self)
        self.save()
        bust_cache('requests', self.to_user.pk)
        return True


class FriendshipQuerySet(QuerySet):
    """ Friendship manager """

    def friends(self, user):
        """ Return a list of all friends """
        key = cache_key('friends', user.pk)
        friends = cache.get(key)

        if friends is None:
            qs = Friend.objects.filter(from_user=user).select_related(max_depth=2)
            friends = [u.to_user for u in qs]
            cache.set(key, friends)

        return friends

    def requests(self, user):
        """ Return a list of friendship requests """
        key = cache_key('requests', user.pk)
        requests = cache.get(key)

        if requests is None:
            qs = FriendshipRequest.objects.filter(
                to_user=user).select_related(max_depth=2)
            requests = list(qs)
            cache.set(key, requests)

        return requests

    def sent_requests(self, user):
        """ Return a list of friendship requests from user """
        key = cache_key('sent_requests', user.pk)
        requests = cache.get(key)

        if requests is None:
            qs = FriendshipRequest.objects.filter(
                from_user=user).select_related(max_depth=2)
            requests = list(qs)
            cache.set(key, requests)

        return requests

    def unread_requests(self, user):
        """ Return a list of unread friendship requests """
        key = cache_key('unread_requests', user.pk)
        unread_requests = cache.get(key)

        if unread_requests is None:
            qs = FriendshipRequest.objects.filter(
                to_user=user,
                viewed=None).select_related(max_depth=2)
            unread_requests = list(qs)
            cache.set(key, unread_requests)

        return unread_requests

    def unread_request_count(self, user):
        """ Return a count of unread friendship requests """
        key = cache_key('unread_request_count', user.pk)
        count = cache.get(key)

        if count is None:
            count = FriendshipRequest.objects.filter(
                to_user=user,
                viewed=None).count()
            cache.set(key, count)

        return count

    def read_requests(self, user):
        """ Return a list of read friendship requests """
        key = cache_key('read_requests', user.pk)
        read_requests = cache.get(key)

        if read_requests is None:
            qs = FriendshipRequest.objects.filter(
                to_user=user,
                viewed__ne=None).select_related(max_depth=2)
            read_requests = list(qs)
            cache.set(key, read_requests)

        return read_requests

    def rejected_requests(self, user):
        """ Return a list of rejected friendship requests """
        key = cache_key('rejected_requests', user.pk)
        rejected_requests = cache.get(key)

        if rejected_requests is None:
            qs = FriendshipRequest.objects.filter(
                to_user=user,
                rejected__ne=None).select_related(max_depth=2)
            rejected_requests = list(qs)
            cache.set(key, rejected_requests)

        return rejected_requests

    def unrejected_requests(self, user):
        """ All requests that haven't been rejected """
        key = cache_key('unrejected_requests', user.pk)
        unrejected_requests = cache.get(key)

        if unrejected_requests is None:
            qs = FriendshipRequest.objects.filter(
                to_user=user,
                rejected=None).select_related(max_depth=2)
            unrejected_requests = list(qs)
            cache.set(key, unrejected_requests)

        return unrejected_requests

    def unrejected_request_count(self, user):
        """ Return a count of unrejected friendship requests """
        key = cache_key('unrejected_request_count', user.pk)
        count = cache.get(key)

        if count is None:
            count = FriendshipRequest.objects.filter(
                to_user=user,
                rejected=None).count()
            cache.set(key, count)

        return count

    def add_friend(self, from_user, to_user, message=None):
        """ Create a friendship request """
        if from_user == to_user:
            raise ValidationError(_("Users cannot be friends with themselves"))

        blocked = Blocking.objects.is_blocked(from_user=to_user, to_user=from_user)
        if blocked:
            raise ValidationError(
                _("You can't invite %(display_name)s to friends.") % {
                    'display_name': to_user.get_display_name()
                }
            )

        # remove any existent blocking
        is_user_was_blocked = Blocking.objects.remove_blocking(
                                    from_user=from_user, to_user=to_user)

        if message is None:
            message = ''

        request = FriendshipRequest.objects(
            from_user=from_user,
            to_user=to_user,
        ).modify(upsert=True, new=False, set__from_user=from_user,
                set__to_user=to_user, set__message=message, set__created=timezone.now())

        if request is not None and not is_user_was_blocked:
            raise AlreadyExistsError("Friendship already requested")

        if request is None:
            request = FriendshipRequest.objects(
                from_user=from_user,
                to_user=to_user).first()
        else:
            request.rejected = None
            request.viewed = None
            request.save()

        bust_cache('requests', to_user.pk)
        bust_cache('sent_requests', from_user.pk)
        friendship_request_created.send(sender=request)

        return request

    def remove_friend(self, to_user, from_user):
        """ Destroy a friendship relationship """
        try:
            qs = Friend.objects.filter(
                Q(to_user=to_user, from_user=from_user) |
                Q(to_user=from_user, from_user=to_user)
            )

            if qs:
                for qs_ in list(qs):
                    kw = {'from_user': None, 'to_user': None}
                    if qs_.from_user == from_user:
                        kw = {'from_user': from_user, 'to_user': to_user}
                    elif qs_.from_user == to_user:
                        kw = {'from_user': to_user, 'to_user': from_user}
                    else:
                        raise ValueError('None of from_user and to_user found in queryset.')

                    kw['sender'] = qs_
                    friendship_removed.send(**kw)
                qs.delete()
                bust_cache('friends', to_user.pk)
                bust_cache('friends', from_user.pk)
                return True
            else:
                return False
        except Friend.DoesNotExist:
            return False

    def are_friends(self, user1, user2):
        """ Are these two users friends? """
        friends1 = cache.get(cache_key('friends', user1.pk))
        friends2 = cache.get(cache_key('friends', user2.pk))
        if friends1 and user2 in friends1:
            return True
        elif friends2 and user1 in friends2:
            return True
        else:
            try:
                Friend.objects.get(to_user=user1, from_user=user2)
                return True
            except Friend.DoesNotExist:
                return False


@python_2_unicode_compatible
class Friend(Document):
    """
    Document to represent Friendships

    Important! Please note, that (from_user=User1, to_user=User2)
        and (from_user=User2, to_user=User1) are not the same!
    """
    from_user = fields.ReferenceField(get_user_model())
    to_user = fields.ReferenceField(get_user_model(), unique_with='from_user')
    created = fields.DateTimeField(default=timezone.now, null=True)
    #tags = fields.ListField(fields.StringField(), required=False)

    meta = {
        'indexes': [
            'to_user',
            'from_user',
            ('from_user', 'to_user'),
        ],
        'queryset_class': FriendshipQuerySet
    }

    class Meta:
        verbose_name = _('Friend')
        verbose_name_plural = _('Friends')

    def __str__(self):
        return "User #%s is friends with #%s" % (self.to_user.pk, self.from_user.pk)

    def save(self, *args, **kwargs):
        # Ensure users can't be friends with themselves
        if self.to_user == self.from_user:
            raise ValidationError("Users cannot be friends with themselves.")
        return super(Friend, self).save(*args, **kwargs)


class InspirationQuerySet(QuerySet):
    """ Inspiration manager """

    def inspired_by_user(self, user):
        """ Return a list of all inspirations """
        key = cache_key('inspirations', user.pk)
        inspirations = cache.get(key)

        if inspirations is None:
            qs = Inspiration.objects.filter(inspired_by=user).select_related(max_depth=2)
            inspirations = [u.user for u in qs]
            cache.set(key, inspirations)

        return inspirations

    def user_inspired_by(self, user):
        """ Return a list of all users the given user follows """
        key = cache_key('inspirationals', user.pk)
        inspirationals = cache.get(key)

        if inspirationals is None:
            qs = Inspiration.objects.filter(user=user).select_related(max_depth=2)
            inspirationals = [u.inspired_by for u in qs]
            cache.set(key, inspirationals)

        return inspirationals

    def add_inspiration(self, user, inspired_by):
        """ Create 'user' inspired by 'inspired_by' relationship """
        if user == inspired_by:
            raise ValidationError("Users cannot inspire themselves")

        relation = Inspiration.objects(user=user, inspired_by=inspired_by)\
            .modify(new=False, upsert=True, set__user=user,
                    set__inspired_by=inspired_by, set__created=timezone.now())

        if relation is not None:
            raise AlreadyExistsError("User '%s' already inspired by '%s'" % (user, inspired_by))

        relation = Inspiration.objects(user=user, inspired_by=inspired_by).first()

        inspirations_created.send(sender=self, user=user)
        inspirationals_created.send(sender=self, inspired_by=inspired_by)

        bust_cache('inspirations', inspired_by.pk)
        bust_cache('inspirationals', user.pk)

        return relation

    def remove_inspiration(self, user, inspired_by):
        """ Remove 'user' inspired by 'inspired_by' relationship """
        try:
            rel = Inspiration.objects.get(user=user, inspired_by=inspired_by)
            inspirations_removed.send(sender=rel, user=rel.user)
            inspirationals_removed.send(sender=rel, inspired_by=rel.inspired_by)
            rel.delete()
            bust_cache('inspirations', inspired_by.pk)
            bust_cache('inspirationals', user.pk)
            return True
        except Inspiration.DoesNotExist:
            return False

    def is_inspired(self, user, inspired_by):
        """ Does user inspired by inspirational? Smartly uses caches if exists """
        inspirations = cache.get(cache_key('inspirationals', user.pk))
        inspirationals = cache.get(cache_key('inspirations', inspired_by.pk))

        if inspirations and inspired_by in inspirations:
            return True
        elif inspirationals and user in inspirationals:
            return True
        else:
            try:
                Inspiration.objects.get(user=user, inspired_by=inspired_by)
                return True
            except Inspiration.DoesNotExist:
                return False


@python_2_unicode_compatible
class Inspiration(Document):
    """
    Model to represent Inspiration relationships

    Notes:
    - inspirations (followers) - people who inspired by me (user)
            (Inspiration.objects(inspired_by=user).only('user'))
    - inspirationals (following) - people who inspire the user
            (Inspiration.objects(user=user).only('inspired_by'))

    TODO:
    1) ensure that (user, inspired_by) and (inspired_by, user) are not the same;
    """
    user = fields.ReferenceField(get_user_model())
    inspired_by = fields.ReferenceField(get_user_model(), unique_with='user')
    created = fields.DateTimeField(default=timezone.now, null=True)

    meta = {
        'indexes': [
            'user',
            'inspired_by',
            ('user', 'inspired_by'),
        ],
        'queryset_class': InspirationQuerySet
    }

    class Meta:
        verbose_name = _('Inspiration Relationship')
        verbose_name_plural = _('Inspiration Relationships')

    def __str__(self):
        return "User #%s inspired by #%s" % (self.user.pk, self.inspired_by.pk)

    def save(self, *args, **kwargs):
        # Ensure users can't be inspired by themselves
        if self.user == self.inspired_by:
            raise ValidationError("Users cannot inspire themselves.")

        return super(Inspiration, self).save(*args, **kwargs)


class BlockingQuerySet(QuerySet):

    def blocked_for_user(self, user):
        key = cache_key('blocked', user.pk)
        blocked = cache.get(key)

        if blocked is None:
            qs = Blocking.objects.filter(from_user=user).select_related(max_depth=2)
            blocked = [u.to_user for u in qs]
            cache.set(key, blocked)

        return blocked

    def add_blocking(self, from_user, to_user):
        """ Create 'from_user' blocked 'to_user' relationship """
        if from_user == to_user:
            raise ValidationError("Users cannot block themselves")

        relation = Blocking.objects(from_user=from_user, to_user=to_user)\
            .modify(new=False, upsert=True, set__from_user=from_user,
                    set__to_user=to_user, set__created=timezone.now())

        Friend.objects.remove_friend(from_user, to_user)

        # reject all requests from `to_user`
        to_user_requests = FriendshipRequest.objects.filter(
            from_user=to_user,
            to_user=from_user)

        for req in to_user_requests:
            req.reject()

        # .. and cancel all requests from 'from_user' to 'to_user'
        from_user_requests = FriendshipRequest.objects.filter(
            from_user=from_user,
            to_user=to_user)

        for req in from_user_requests:
            req.cancel()

        if relation is not None:
            raise AlreadyExistsError("User '%s' already blocked '%s'" % (from_user, to_user))

        relation = Blocking.objects(from_user=from_user, to_user=to_user).first()

        blocking_created.send(sender=self, from_user=from_user, to_user=to_user)

        bust_cache('blocked', from_user.pk)

        return relation

    def remove_blocking(self, from_user, to_user):
        """ Remove 'user' blocked 'to_user' relationship """
        try:
            rel = Blocking.objects.get(from_user=from_user, to_user=to_user)
            blocking_removed.send(sender=rel, from_user=rel.from_user, to_user=rel.to_user)
            rel.delete()
            bust_cache('blocked', from_user.pk)
            return True
        except Blocking.DoesNotExist:
            return False

    def is_blocked(self, from_user, to_user):
        """ Is to_user blocked by from_user? """
        blocked = cache.get(cache_key('blocked', from_user.pk))
        if blocked and to_user in blocked:
            return True
        else:
            try:
                Blocking.objects.get(from_user=from_user, to_user=to_user)
                return True
            except Blocking.DoesNotExist:
                return False


@python_2_unicode_compatible
class Blocking(Document):
    """
    A blocking is used to block user from sending invitations to another user
    (to protect from invitation spamming).
    """

    from_user = fields.ReferenceField(
        get_user_model(),
        verbose_name=_("from user"))
    to_user = fields.ReferenceField(
        get_user_model(),
        unique_with='from_user',
        verbose_name=_("to user"))
    created = fields.DateTimeField(
        verbose_name=_("created"),
        default=timezone.now)

    meta = {
        'indexes': [
            'from_user',
            'to_user',
            ('from_user', 'to_user')
        ],
        'queryset_class': BlockingQuerySet
    }

    def __str__(self):
        return "User #{} blocked #{}".format(
            self.from_user, self.to_user)



# signals receivers to send notifications

if "notification" in settings.INSTALLED_APPS:
    from notification import models as notification
else:
    notification = None

def send_request_sent_notification(sender, instance, created, **kwargs):
    if notification and created:
        notification.send([instance.to_user],
            "friendship_request", {"request": instance})
        notification.send([instance.from_user],
            "friendship_request_sent", {"request": instance})

def send_acceptance_sent_notification(sender, instance, created, **kwargs):
    if notification and created:
        notification.send([instance.to_user],
            "friendship_accept_sent", {"from_user": instance.from_user})
        notification.send([instance.from_user],
            "friendship_accept", {"to_user": instance.to_user})

def send_otherconnect_notification(sender, instance, created, **kwargs):
    if notification and created:
        for user in Friend.objects.friends(instance.to_user):
            if user != instance.from_user:
                notification.send([user],
                    "friendship_otherconnect",
                    {"your_friend": instance.to_user,
                    "new_friend": instance.from_user})

        for user in Friend.objects.friends(instance.from_user):
            if user != instance.to_user:
                notification.send([user],
                    "friendship_otherconnect",
                    {"your_friend": instance.from_user,
                    "new_friend": instance.to_user})

def send_friend_removed_notification(sender, instance, **kwargs):
    if notification:
        notification.send([instance.to_user],
            "friendship_friend_removed",
            {"removed_friend": instance.from_user})

        notification.send([instance.from_user],
            "friendship_friend_removed",
            {"removed_friend": instance.to_user})



if notification and USE_NOTIFICATION_APP:

    signals.post_save.connect(
        send_request_sent_notification,
        sender=FriendshipRequest,
        dispatch_uid="friendship_send_request_sent_notification")

    signals.post_save.connect(
        send_acceptance_sent_notification,
        sender=Friend,
        dispatch_uid="friendship_send_acceptance_sent_notification")

    if NOTIFY_ABOUT_NEW_FRIENDS_OF_FRIEND:
        signals.post_save.connect(
            send_otherconnect_notification,
            sender=Friend,
            dispatch_uid="friendship_send_otherconnect_notification")

    if NOTIFY_ABOUT_FRIENDS_REMOVAL:
        signals.pre_delete.connect(
            send_friend_removed_notification,
            sender=Friend,
            dispatch_uid="friendship_send_friend_removed_notification")
