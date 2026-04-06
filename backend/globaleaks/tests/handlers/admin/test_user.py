from twisted.internet.defer import inlineCallbacks

from globaleaks import models
from globaleaks.handlers.admin import user
from globaleaks.handlers.whistleblower.submission import db_assign_submission_progressive
from globaleaks.orm import transact
from globaleaks.rest import errors
from globaleaks.tests import helpers
from globaleaks.utils.crypto import GCE
from globaleaks.utils.utility import datetime_now


class TestUserStats(helpers.TestHandlerWithPopulatedDB):
    _handler = user.UserStats

    @inlineCallbacks
    def test_get(self):
        """Test getting user stats returns report counts"""
        handler = self.request(role='admin')
        response = yield handler.get(self.dummyReceiver_1['id'])

        self.assertIn('total_reports', response)
        self.assertIn('exclusive_reports', response)
        self.assertIsInstance(response['total_reports'], int)
        self.assertIsInstance(response['exclusive_reports'], int)


class TestAdminCollection(helpers.TestCollectionHandler):
    _handler = user.UsersCollection
    _test_desc = {
        'model': models.User,
        'create': user.create_user,
        'data': {
            'role': 'admin',
            'name': 'Mario Rossi',
            'mail_address': 'admin@theguardian.com',
            'language': 'en',
            'send_activation_link': True
        }
    }

    def get_dummy_request(self):
        data = helpers.TestCollectionHandler.get_dummy_request(self)
        data['role'] = self._test_desc['data']['role']
        data['roles'] = [self._test_desc['data']['role']]
        data['pgp_key_remove'] = False
        return data


class TestAdminInstance(helpers.TestInstanceHandler):
    _handler = user.UserInstance
    _test_desc = {
        'model': models.User,
        'create': user.create_user,
        'data': {
            'role': 'admin',
            'mail_address': 'admin@theguardian.com',
            'language': 'en',
            'send_activation_link': True
        }
    }

    @inlineCallbacks
    def setUp(self):
        yield helpers.TestHandlerWithPopulatedDB.setUp(self)

    def get_dummy_request(self):
        data = helpers.TestInstanceHandler.get_dummy_request(self)
        data['role'] = self._test_desc['data']['role']
        data['roles'] = [self._test_desc['data']['role']]
        data['pgp_key_remove'] = False
        return data

    @transact
    def create_report_for_user(self, session, user_id):
        context_id = session.query(models.Context.id).filter(
            models.Context.tid == 1
        ).first()

        if context_id is None:
            questionnaire = models.Questionnaire()
            questionnaire.tid = 1
            questionnaire.name = 'delete-test-questionnaire'
            session.add(questionnaire)
            session.flush()

            context = models.Context()
            context.tid = 1
            context.name = {'en': 'Delete Test Context'}
            context.description = {'en': 'Delete Test Description'}
            context.questionnaire_id = questionnaire.id
            session.add(context)
            session.flush()
            context_id = context.id
        else:
            context_id = context_id[0]

        itip = models.InternalTip()
        itip.context_id = context_id
        itip.tid = 1
        itip.progressive = db_assign_submission_progressive(session, 1)
        itip.status = 'opened'
        itip.expiration_date = datetime_now()
        itip.creation_date = datetime_now()
        itip.update_date = datetime_now()
        itip.last_access = datetime_now()
        itip.receipt_hash = GCE.generate_receipt()
        itip.crypto_prv_key = 'test_prv_key'
        itip.crypto_pub_key = 'test_pub_key'
        itip.crypto_tip_pub_key = 'test_tip_pub_key'
        itip.crypto_tip_prv_key = 'test_tip_prv_key'
        itip.deprecated_crypto_files_pub_key = 'test_files_pub_key'
        session.add(itip)
        session.flush()

        rtip = models.ReceiverTip()
        rtip.internaltip_id = itip.id
        rtip.receiver_id = user_id
        session.add(rtip)
        session.flush()

    @inlineCallbacks
    def get_delete_request(self, user_id):
        yield self.create_report_for_user(user_id)
        stats_handler = self.request(role='admin', handler_cls=user.UserStats)
        stats = yield stats_handler.get(user_id)

        return {
            'expected_total': stats['total_reports'],
            'expected_exclusive': stats['exclusive_reports'],
            'expected_last_update': stats['last_update']
        }

    @inlineCallbacks
    def test_delete(self):
        data = self.get_dummy_request()
        data = yield self._test_desc['create'](1, self.session, data, 'en')

        request = yield self.get_delete_request(data['id'])
        handler = self.request(request, role='admin')
        yield handler.delete(data['id'])


class TestReceiverCollection(TestAdminCollection):
    _test_desc = {
        'model': models.User,
        'create': user.create_user,
        'data': {
            'role': 'receiver',
            'name': 'Mario Rossi',
            'mail_address': 'receiver@theguardian.com',
            'language': 'en',
            'send_activation_link': True
        }
    }


class TestReceiverInstance(TestAdminInstance):
    _test_desc = {
        'model': models.User,
        'create': user.create_user,
        'data': {
            'role': 'receiver',
            'name': 'Mario Rossi',
            'mail_address': 'receiver@theguardian.com',
            'language': 'en',
            'send_activation_link': True
        }
    }

    @inlineCallbacks
    def test_delete_soft_deletes_user(self):
        receiver = yield user.create_user(1, self.session, self.get_dummy_request(), 'en')
        request = yield self.get_delete_request(receiver['id'])
        handler = self.request(request, role='admin')
        yield handler.delete(receiver['id'])

        @transact
        def check_user_status(session):
            deleted_user = session.query(models.User).filter(
                models.User.id == receiver['id']
            ).one()
            return deleted_user.status

        status = yield check_user_status()
        self.assertEqual(status, 'deleted')

    @inlineCallbacks
    def test_delete_with_mismatched_stats(self):
        receiver = yield user.create_user(1, self.session, self.get_dummy_request(), 'en')
        request = yield self.get_delete_request(receiver['id'])
        request['expected_total'] += 1

        handler = self.request(request, role='admin')
        yield self.assertFailure(handler.delete(receiver['id']), errors.UserStatsChanged)


class TestCustodianCollection(TestAdminCollection):
    _test_desc = {
        'model': models.User,
        'create': user.create_user,
        'data': {
            'role': 'custodian',
            'name': 'Mario Rossi',
            'mail_address': 'custodian@theguardian.com',
            'language': 'en',
            'send_activation_link': True
        }
    }


class TestCustodianInstance(TestAdminInstance):
    _test_desc = {
        'model': models.User,
        'create': user.create_user,
        'data': {
            'role': 'custodian',
            'mail_address': 'custodian@theguardian.com',
            'language': 'en'
        }
    }
