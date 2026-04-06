from twisted.internet.defer import inlineCallbacks

from globaleaks import models
from globaleaks.handlers.admin import tenant
from globaleaks.handlers.whistleblower.submission import db_assign_submission_progressive
from globaleaks.models import config
from globaleaks.orm import transact, tw
from globaleaks.rest import errors
from globaleaks.tests import helpers
from globaleaks.utils.crypto import GCE
from globaleaks.utils.utility import datetime_now


def get_dummy_tenant_desc():
    return {
        'label': 'tenant-xxx',
        'active': True,
        'name': 'GlobaLeaks',
        'mode': 'default',
        'subdomain': 'subdomain',
        'profile': 'default'
    }


class TestTenantCollection(helpers.TestHandlerWithPopulatedDB):
    _handler = tenant.TenantCollection

    @inlineCallbacks
    def test_get(self):
        n = 3

        for i in range(n):
            yield tenant.create(get_dummy_tenant_desc())

        handler = self.request(role='admin')
        response = yield handler.get()

        self.assertEqual(len(response), self.population_of_tenants + n)

    @inlineCallbacks
    def test_post(self):
        r = {}
        for i in range(0, 3):
            handler = self.request(get_dummy_tenant_desc(), role='admin')
            t = yield handler.post()
            r[i] = yield tw(config.db_get_config_variable, t['id'], 'receipt_salt')

        # Checks that the salt is actually modified from create to another
        self.assertNotEqual(r[0], r[1])
        self.assertNotEqual(r[1], r[2])
        self.assertNotEqual(r[2], r[0])


class TestTenantInstance(helpers.TestHandlerWithPopulatedDB):
    _handler = tenant.TenantInstance

    @inlineCallbacks
    def setUp(self):
        yield helpers.TestHandlerWithPopulatedDB.setUp(self)
        t = yield tenant.create_and_initialize(get_dummy_tenant_desc())
        t['profile'] = 'default'
        self.tenant_id = t['id']
        self.handler = self.request(t, role='admin')

    @transact
    def create_tenant_report(self, session, tid):
        context_id = session.query(models.Context.id).filter(
            models.Context.tid == tid
        ).first()[0]

        itip = models.InternalTip()
        itip.context_id = context_id
        itip.tid = tid
        itip.progressive = db_assign_submission_progressive(session, tid)
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

    @inlineCallbacks
    def get_delete_request(self):
        yield self.create_tenant_report(self.tenant_id)
        stats = yield tenant.get_tenant_stats(self.tenant_id)

        return {
            'expected_open': stats['open_reports'],
            'expected_total': stats['total_reports'],
            'expected_last_update': stats['last_update']
        }

    def test_get(self):
        return self.handler.get(self.tenant_id)

    def test_put(self):
        return self.handler.put(self.tenant_id)

    @inlineCallbacks
    def test_delete(self):
        request = yield self.get_delete_request()
        handler = self.request(request, role='admin')
        yield handler.delete(self.tenant_id)

    @inlineCallbacks
    def test_delete_with_valid_stats(self):
        """Test deletion succeeds when expected stats match current stats"""
        request = yield self.get_delete_request()
        handler = self.request(request, role='admin')
        yield handler.delete(self.tenant_id)

    @inlineCallbacks
    def test_delete_with_mismatched_stats(self):
        """Test deletion fails when expected stats don't match current stats"""
        request = yield self.get_delete_request()
        request['expected_open'] += 1
        request['expected_total'] += 1

        handler = self.request(request, role='admin')
        yield self.assertFailure(handler.delete(self.tenant_id), errors.TenantStatsChanged)


class TestTenantStats(helpers.TestHandlerWithPopulatedDB):
    _handler = tenant.TenantStats

    @inlineCallbacks
    def setUp(self):
        yield helpers.TestHandlerWithPopulatedDB.setUp(self)
        t = yield tenant.create(get_dummy_tenant_desc())
        self.tenant_id = t['id']

    @inlineCallbacks
    def test_get(self):
        """Test retrieving tenant stats"""
        handler = self.request(role='admin')
        response = yield handler.get(self.tenant_id)

        self.assertIn('open_reports', response)
        self.assertIn('total_reports', response)
        self.assertIn('last_update', response)
        self.assertIsInstance(response['open_reports'], int)
        self.assertIsInstance(response['total_reports'], int)
        self.assertTrue(response['last_update'] is None or isinstance(response['last_update'], str))
        self.assertGreaterEqual(response['total_reports'], response['open_reports'])
