Distinctions
============

* overwritten for ``MongoEngine``
* only business logic: no views, templates, templatetags and urls
* added ``Blocking`` model: users in that model cannot be added to friends
* added compat.py
* Follow was replaced by Inspiration
* initial support for django-notification (https://github.com/jtauber/django-notification): supports only friends relations now


TODO
====

- full support of django-notification: Blocking and Inspiration
- add suggestion feature (like in https://github.com/Thinktiv/django-easy-friends)



django-friendship
=================

.. image:: https://secure.travis-ci.org/revsys/django-friendship.png
    :alt: Build Status
    :target: http://travis-ci.org/revsys/django-friendship

Usage
=====

Add ``friendship`` to ``INSTALLED_APPS`` and run ``syncdb``.

To use ``django-friendship`` in your views::

    from path_to_your_custom_user.models import User
    from friendship.models import Friend, Inspiration

    def my_view(request):
        # List of this user's friends
        all_friends = Friend.objects.friends(request.user)

        # List all unread friendship requests
        requests = Friend.objects.unread_requests(user=request.user)

        # List all rejected friendship requests
        rejects = Friend.objects.rejected_requests(user=request.user)

        # Count of all rejected friendship requests
        reject_count = Friend.objects.rejected_request_count(user=request.user)

        # List all unrejected friendship requests
        unrejects = Friend.objects.unrejected_requests(user=request.user)

        # Count of all unrejected friendship requests
        unreject_count = Friend.objects.unrejected_request_count(user=request.user)

        # List all sent friendship requests
        sent = Friend.objects.sent_requests(user=request.user)

        # List of this user's followers
        all_followers = Inspiration.objects.inspired_by_user(request.user)

        # List of who this user is following
        following = Inspiration.objects.user_inspired_by(request.user)

        ### Managing friendship relationships

        # Create a friendship request
        other_user = User.objects.all()[0]
        new_relationship = Friend.objects.add_friend(request.user, other_user)

        # Can optionally save a message when creating friend requests
        message_relationship = Friend.objects.add_friend(
            from_user=request.user,
            to_user=some_other_user,
            message='Hi, I would like to be your friend',
        )

        # And immediately accept it, normally you would give this option to the user
        new_relationship.accept()

        # Now the users are friends
        Friend.objects.are_friends(request.user, other_user) == True

        # Remove the friendship
        Friend.objects.remove_friend(other_user, request.user)

        # Create request.user follows other_user relationship
        following_created = Inspiration.objects.add_inspiration(request.user, other_user)

Signals
=======

``django-friendship`` emits the following signals:

* friendship_request_created
* friendship_request_rejected
* friendship_request_canceled
* friendship_request_accepted
* friendship_removed
* blocking_created
* blocking_removed
* inspirations_created
* inspirations_removed
* inspirationals_created
* inspirationals_removed

Compatibility
=============

This package requires Django 1.6 and above.
