from django.core.cache import cache
from django.core.exceptions import ValidationError
#from django.db import IntegrityError

from mongoengine.django.tests import MongoTestCase
from mongoengine.errors import NotUniqueError

from friendship.compat import get_user_model
from friendship.exceptions import AlreadyExistsError
from friendship.models import Friend, Inspiration, Blocking, FriendshipRequest


class login(object):
    def __init__(self, testcase, user, password):
        self.testcase = testcase
        success = testcase.client.login(username=user, password=password)
        self.testcase.assertTrue(
            success,
            "login with username=%r, password=%r failed" % (user, password)
        )

    def __enter__(self):
        pass

    def __exit__(self, *args):
        self.testcase.client.logout()


class BaseTestCase(MongoTestCase):

    def setUp(self):
        """
        Setup some initial users

        """
        self.User = get_user_model()
        self.User.drop_collection()
        self.user_pw = 'test'
        self.user_bob = self.create_user('bob@bob.com', self.user_pw)
        self.user_steve = self.create_user('steve@steve.com', self.user_pw)
        self.user_susan = self.create_user('susan@susan.com', self.user_pw)
        self.user_amy = self.create_user('amy@amy.amy.com', self.user_pw)
        cache.clear()

        Friend.drop_collection()
        Inspiration.drop_collection()
        FriendshipRequest.drop_collection()

    def tearDown(self):
        cache.clear()
        #self.client.logout()
        self.User.drop_collection()
        Friend.drop_collection()
        Inspiration.drop_collection()
        FriendshipRequest.drop_collection()

    def login(self, user, password):
        return login(self, user, password)

    def create_user(self, email_address, password):
        user = self.User.objects.create_user(email=email_address, password=password)
        return user


class FriendshipModelTests(BaseTestCase):

    def test_friendship_request(self):
        ### Bob wants to be friends with Steve
        req1 = Friend.objects.add_friend(self.user_bob, self.user_steve)

        # Ensure neither have friends already
        self.assertEqual(Friend.objects.friends(self.user_bob), [])
        self.assertEqual(Friend.objects.friends(self.user_steve), [])

        # Ensure FriendshipRequest is created
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_steve), 1)

        # Ensure the proper sides have requests or not
        self.assertEqual(len(Friend.objects.requests(self.user_bob)), 0)
        self.assertEqual(len(Friend.objects.requests(self.user_steve)), 1)
        self.assertEqual(len(Friend.objects.sent_requests(self.user_bob)), 1)
        self.assertEqual(len(Friend.objects.sent_requests(self.user_steve)), 0)

        self.assertEqual(len(Friend.objects.unread_requests(self.user_steve)), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_steve), 1)

        self.assertEqual(len(Friend.objects.rejected_requests(self.user_steve)), 0)

        self.assertEqual(len(Friend.objects.unrejected_requests(self.user_steve)), 1)
        self.assertEqual(Friend.objects.unrejected_request_count(self.user_steve), 1)

        # Ensure they aren't friends at this point
        self.assertFalse(Friend.objects.are_friends(self.user_bob, self.user_steve))

        # Accept the request
        req1.accept()

        # Ensure neither have pending requests
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 0)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 0)

        # Ensure both are in each other's friend lists
        self.assertEqual(Friend.objects.friends(self.user_bob), [self.user_steve])
        self.assertEqual(Friend.objects.friends(self.user_steve), [self.user_bob])
        self.assertTrue(Friend.objects.are_friends(self.user_bob, self.user_steve))

        # Make sure we can remove friendship
        self.assertTrue(Friend.objects.remove_friend(self.user_bob, self.user_steve))
        self.assertFalse(Friend.objects.are_friends(self.user_bob, self.user_steve))
        self.assertFalse(Friend.objects.remove_friend(self.user_bob, self.user_steve))

        # Susan wants to be friends with Amy, but cancels it
        req2 = Friend.objects.add_friend(self.user_susan, self.user_amy)
        self.assertEqual(Friend.objects.friends(self.user_susan), [])
        self.assertEqual(Friend.objects.friends(self.user_amy), [])
        req2.cancel()
        self.assertEqual(Friend.objects.requests(self.user_susan), [])
        self.assertEqual(Friend.objects.requests(self.user_amy), [])

        # Susan wants to be friends with Amy, but Amy rejects it
        req3 = Friend.objects.add_friend(self.user_susan, self.user_amy)
        self.assertEqual(Friend.objects.friends(self.user_susan), [])
        self.assertEqual(Friend.objects.friends(self.user_amy), [])
        req3.reject()

        # Duplicated requests raise a more specific subclass of IntegrityError.
        with self.assertRaises(NotUniqueError):
            FriendshipRequest.objects.create(from_user=self.user_susan, to_user=self.user_amy)

        with self.assertRaises(AlreadyExistsError):
            Friend.objects.add_friend(self.user_susan, self.user_amy)

        self.assertFalse(Friend.objects.are_friends(self.user_susan, self.user_amy))
        self.assertEqual(len(Friend.objects.rejected_requests(self.user_amy)), 1)
        self.assertEqual(len(Friend.objects.rejected_requests(self.user_amy)), 1)

        # let's try that again..
        req3.delete()

        # Susan wants to be friends with Amy, and Amy reads it
        req4 = Friend.objects.add_friend(self.user_susan, self.user_amy)
        req4.mark_viewed()

        self.assertFalse(Friend.objects.are_friends(self.user_susan, self.user_amy))
        self.assertEqual(len(Friend.objects.read_requests(self.user_amy)), 1)

        # Ensure we can't be friends with ourselves
        with self.assertRaises(ValidationError):
            Friend.objects.add_friend(self.user_bob, self.user_bob)

        # Ensure we can't do it manually either
        with self.assertRaises(ValidationError):
            Friend.objects.create(to_user=self.user_bob, from_user=self.user_bob)

    def test_multiple_friendship_requests(self):
        """ Ensure multiple friendship requests are handled properly """
        ### Bob wants to be friends with Steve
        req1 = Friend.objects.add_friend(self.user_bob, self.user_steve)

        # Ensure neither have friends already
        self.assertEqual(Friend.objects.friends(self.user_bob), [])
        self.assertEqual(Friend.objects.friends(self.user_steve), [])

        # Ensure FriendshipRequest is created
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_steve), 1)

        # Steve also wants to be friends with Bob before Bob replies
        req2 = Friend.objects.add_friend(self.user_steve, self.user_bob)

        # Ensure they aren't friends at this point
        self.assertFalse(Friend.objects.are_friends(self.user_bob, self.user_steve))

        # Ensure FriendshipRequest is created
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_steve).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_bob).count(), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_bob), 1)

        # Accept the request
        req1.accept()

        # Ensure neither have pending requests
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 0)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 0)
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_steve).count(), 0)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_bob).count(), 0)

    def test_blocking(self):
        # Users cannot block themselves
        with self.assertRaises(ValidationError):
            Blocking.objects.add_blocking(self.user_bob, self.user_bob)

    def test_blocking_for_friends(self):
        ### Bob and Steve are friends
        req1 = Friend.objects.add_friend(self.user_bob, self.user_steve)
        req1.accept()

        # Ensure they are friends
        self.assertTrue(Friend.objects.are_friends(self.user_bob, self.user_steve))

        # Bob has decided to block his friend Steve
        Blocking.objects.add_blocking(self.user_bob, self.user_steve)

        # Is Steve really blocked?
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_bob), [self.user_steve])
        self.assertTrue(Blocking.objects.is_blocked(self.user_bob, self.user_steve))

        # In this case, Bob isn't blocked by Steve
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_steve), [])
        self.assertFalse(Blocking.objects.is_blocked(self.user_steve, self.user_bob))

        # .. now they aren't friends
        self.assertFalse(Friend.objects.are_friends(self.user_bob, self.user_steve))

        # Ensure neither have friends
        self.assertEqual(Friend.objects.friends(self.user_bob), [])
        self.assertEqual(Friend.objects.friends(self.user_steve), [])

    def test_blocking_for_requests(self):
        ### Bob and Steve aren't friends
        req1 = Friend.objects.add_friend(self.user_bob, self.user_steve)

        # Ensure neither have friends already
        self.assertEqual(Friend.objects.friends(self.user_bob), [])
        self.assertEqual(Friend.objects.friends(self.user_steve), [])

        # Ensure FriendshipRequest is created
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_steve), 1)

        # Bob is a spammer and Steve has blocked him
        Blocking.objects.add_blocking(self.user_steve, self.user_bob)

        # Is Bob really blocked?
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_steve), [self.user_bob])
        self.assertTrue(Blocking.objects.is_blocked(self.user_steve, self.user_bob))

        # In this case, Steve isn't blocked by Bob
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_bob), [])
        self.assertFalse(Blocking.objects.is_blocked(self.user_bob, self.user_steve))

        # Ensure FriendshipRequest is rejected
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_steve), 1)
        self.assertEqual(Friend.objects.rejected_requests(self.user_steve), [req1])

    def test_blocking_for_multiple_requests(self):
        ### Bob and Steve aren't friends
        req1 = Friend.objects.add_friend(self.user_bob, self.user_steve)
        req2 = Friend.objects.add_friend(self.user_steve, self.user_bob)

        # Ensure neither have friends already
        self.assertEqual(Friend.objects.friends(self.user_bob), [])
        self.assertEqual(Friend.objects.friends(self.user_steve), [])

        # Ensure FriendshipRequest is created
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_steve).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_bob).count(), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_steve), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_bob), 1)

        # Bob is a spammer and Steve has blocked him
        Blocking.objects.add_blocking(self.user_steve, self.user_bob)

        # Is Bob really blocked?
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_steve), [self.user_bob])
        self.assertTrue(Blocking.objects.is_blocked(self.user_steve, self.user_bob))

        # In this case, Steve isn't blocked by Bob
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_bob), [])
        self.assertFalse(Blocking.objects.is_blocked(self.user_bob, self.user_steve))

        # Ensure FriendshipRequest is rejected
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 1)
        self.assertEqual(Friend.objects.requests(self.user_steve), [req1])
        self.assertEqual(Friend.objects.rejected_requests(self.user_steve), [req1])

        # Ensure FriendshipRequest is canceled
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_steve).count(), 0)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_bob).count(), 0)
        self.assertEqual(Friend.objects.requests(self.user_bob), [])

    def test_blocking_before_request(self):
        Blocking.objects.add_blocking(self.user_bob, self.user_steve)

        # Is Steve really blocked?
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_bob), [self.user_steve])
        self.assertTrue(Blocking.objects.is_blocked(self.user_bob, self.user_steve))

        # In this case, Bob isn't blocked by Steve
        self.assertEqual(Blocking.objects.blocked_for_user(self.user_steve), [])
        self.assertFalse(Blocking.objects.is_blocked(self.user_steve, self.user_bob))

        # Steve try to add Bob to friends
        # .. but he is spammer and blocked by Bob
        with self.assertRaises(ValidationError):
            Friend.objects.add_friend(self.user_steve, self.user_bob)

        # But Bob does
        req1 = Friend.objects.add_friend(self.user_bob, self.user_steve)

        # and now Steve isn't blocked by Bob
        self.assertFalse(Blocking.objects.is_blocked(self.user_bob, self.user_steve))

        # Ensure requests is created
        self.assertEqual(FriendshipRequest.objects.filter(from_user=self.user_bob).count(), 1)
        self.assertEqual(FriendshipRequest.objects.filter(to_user=self.user_steve).count(), 1)
        self.assertEqual(Friend.objects.unread_request_count(self.user_steve), 1)
        self.assertEqual(Friend.objects.rejected_requests(self.user_steve), [])

    def test_inspiration(self):
        # Bob inspired by Steve
        req1 = Inspiration.objects.add_inspiration(self.user_bob, self.user_steve)
        self.assertEqual(len(Inspiration.objects.inspired_by_user(self.user_steve)), 1)
        self.assertEqual(len(Inspiration.objects.user_inspired_by(self.user_bob)), 1)
        self.assertEqual(Inspiration.objects.inspired_by_user(self.user_steve), [self.user_bob])
        self.assertEqual(Inspiration.objects.user_inspired_by(self.user_bob), [self.user_steve])

        self.assertTrue(Inspiration.objects.is_inspired(self.user_bob, self.user_steve))
        self.assertFalse(Inspiration.objects.is_inspired(self.user_steve, self.user_bob))

        # Duplicated requests raise a more specific subclass of IntegrityError.
        with self.assertRaises(NotUniqueError):
            Inspiration.objects.create(user=self.user_bob, inspired_by=self.user_steve)

        # Ensure Inspiration is bi-directional (user_bob inspired by user_steve
        # is not the same as user_steve inspired by user_bob)
        # If not, raises NotUniqueError
        Inspiration.objects.create(inspired_by=self.user_bob, user=self.user_steve)

        with self.assertRaises(AlreadyExistsError):
            Inspiration.objects.add_inspiration(self.user_bob, self.user_steve)

        # Remove the relationship
        self.assertTrue(Inspiration.objects.remove_inspiration(self.user_bob, self.user_steve))
        self.assertEqual(len(Inspiration.objects.inspired_by_user(self.user_steve)), 0)
        self.assertEqual(len(Inspiration.objects.user_inspired_by(self.user_bob)), 0)
        self.assertFalse(Inspiration.objects.is_inspired(self.user_bob, self.user_steve))

        # Ensure we canot follow ourselves
        with self.assertRaises(ValidationError):
            Inspiration.objects.add_inspiration(self.user_bob, self.user_bob)

        with self.assertRaises(ValidationError):
            Inspiration.objects.create(user=self.user_bob, inspired_by=self.user_bob)
