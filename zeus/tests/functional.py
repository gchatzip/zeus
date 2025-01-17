# -*- coding: utf-8 -*-

import os
import datetime
import json
import zipfile
from itertools import izip, chain
from random import shuffle, sample, randint, choice
from datetime import timedelta

from django.test import TransactionTestCase as TestCase
from django.conf import settings
from django.core import mail

from helios import datatypes
from helios.crypto.elgamal import DLog_challenge_generator
from helios.crypto import algs
from helios.views import ELGAMAL_PARAMS
from helios.models import Election, Voter, Poll, Trustee
from zeus.tests.utils import SetUpAdminAndClientMixin
from zeus.core import to_relative_answers, gamma_encode, prove_encryption


class TestElectionBase(SetUpAdminAndClientMixin, TestCase):

    def setUp(self):
        super(TestElectionBase, self).setUp()
        self.local_verbose = os.environ.get('ZEUS_TESTS_VERBOSE', None)
        self.celebration = (
            " _________ ___  __\n"
            "|\   __  \|\  \|\  \\\n"
            "\ \  \ \  \ \  \/  /_\n"
            " \ \  \ \  \ \   ___ \\\n"
            "  \ \  \_\  \ \  \\\ \ \\ \n"
            "   \ \_______\ \__\\\ \_\\\n"
            "    \|_______|\|__| \|_|\n"
            )

        conf = settings.ZEUS_TESTS_ELECTION_PARAMS
        # set the voters number that will be produced for test
        self.voters_num = conf.get('NR_VOTERS', 2)
        # set the trustees number that will be produced for the test
        trustees_num = conf.get('NR_TRUSTEES', 2)
        trustees = "\n".join(",".join(['testName%x testSurname%x' % (x, x),
                   'test%x@mail.com' % x]) for x in range(0, trustees_num))
        # set the polls number that will be produced for the test
        self.polls_number = conf.get('NR_POLLS', 2)
        # set the number of max questions for simple election
        self.simple_election_max_questions_number =\
            conf.get('SIMPLE_MAX_NR_QUESTIONS', 2)
        # set the number of max answers for each question of simple election
        self.simple_election_max_answers_number =\
            conf.get('SIMPLE_MAX_NR_ANSWERS', 2)
        # set the number of max answers in score election
        self.score_election_max_answers =\
            conf.get('SCORE_MAX_NR_ANSWERS', 2)
        # set the number of max questions in party election
        self.party_election_max_questions_number =\
            conf.get('PARTY_MAX_NR_QUESTIONS', 2)
        # set the number of max answers in party election
        self.party_election_max_answers_number =\
            conf.get('PARTY_MAX_NR_ANSWERS', 2)
        # set the number of max candidates in stv election
        self.stv_election_max_answers_number =\
            conf.get('STV_MAX_NR_CANDIDATES', 2)

        start_date = datetime.datetime.now() + timedelta(hours=48)
        end_date = datetime.datetime.now() + timedelta(hours=56)

        self.election_form = {
            'trial': conf.get('trial', False),
            'name': 'test_election',
            'description': 'testing_election',
            'trustees': trustees,
            'voting_starts_at_0': start_date.strftime('%Y-%m-%d'),
            'voting_starts_at_1': start_date.strftime('%H:%M'),
            'voting_ends_at_0': end_date.strftime('%Y-%m-%d'),
            'voting_ends_at_1': end_date.strftime('%H:%M'),
            'help_email': 'test@test.com',
            'help_phone': 6988888888,
            'communication_language': conf.get('com_lang', 'en'),
            }

    def verbose(self, message):
        if self.local_verbose:
            print message

    def get_voter_from_url(self, url):
        chunks = url.split('/')
        uuid = chunks[8]
        voter = Voter.objects.get(uuid=uuid)
        return voter

    def election_form_with_wrong_dates(self):
        self.election_form['election_module'] = self.election_type
        # election number must be 0 before correct form submit
        self.assertEqual(Election.objects.all().count(), 0)
        self.c.post(self.locations['login'], self.login_data)

        # no starting date
        corrupted_form = self.election_form.copy()
        corrupted_form['voting_starts_at_0'] = ""
        r = self.c.post(self.locations['create'], corrupted_form, follow=True)
        self.assertFormError(r, 'form', 'voting_starts_at',
                             'This field is required.')
        self.assertEqual(Election.objects.all().count(), 0)

        # no ending date
        corrupted_form = self.election_form.copy()
        corrupted_form['voting_ends_at_0'] = ""
        r = self.c.post(self.locations['create'], corrupted_form, follow=True)
        self.assertFormError(r, 'form', 'voting_ends_at',
                             'This field is required.')
        self.assertEqual(Election.objects.all().count(), 0)

        # corrupted starting date
        corrupted_form = self.election_form.copy()
        corrupted_form['voting_starts_at_0'] = "2014-12"
        r = self.c.post(self.locations['create'], corrupted_form, follow=True)
        self.assertFormError(r, 'form', 'voting_starts_at',
                             'Wrong date or time format')
        self.assertEqual(Election.objects.all().count(), 0)

        # corrupted ending date
        corrupted_form = self.election_form.copy()
        corrupted_form['voting_ends_at_0'] = "2014-12"
        r = self.c.post(self.locations['create'], corrupted_form, follow=True)
        self.assertFormError(r, 'form', 'voting_ends_at',
                             'Wrong date or time format')
        self.assertEqual(Election.objects.all().count(), 0)

    def admin_can_submit_election_form(self):
        self.election_form['election_module'] = self.election_type
        '''
        self.assertRaises(
            IndexError,
            self.election_form_must_have_trustees,
            self.election_form)
        if self.local_verbose:
            print "Election form without trustees was not accepted"
        '''

        if self.election_type == 'stv':

            self.assertRaises(
                IndexError,
                self.stv_election_form_must_have_departments,
                self.election_form)
            self.verbose('- STV election form was not submited '
                         'without departments')

            self.election_form['departments'] = self.departments
        # Elections number must be 0 before form submit
        self.assertEqual(Election.objects.all().count(), 0)
        self.c.post(self.locations['login'], self.login_data)
        self.c.post(self.locations['create'], self.election_form, follow=True)
        e = Election.objects.all()[0]
        self.e_uuid = e.uuid
        self.assertIsInstance(e, Election)
        self.verbose('+ Admin posted election form')

    '''
    election can have 0 trustees
    def election_form_must_have_trustees(self, post_data):
        post_data['trustess'] = ''
        r = self.c.get(self.locations['login'], self.login_data)
        print r.status_code
        self.election_form['election_module'] = self.election_type
        self.c.post(self.locations['create'], self.election_form, follow=True)
        e = Election.objects.all()[0]
    '''
    def stv_election_form_must_have_departments(self, post_data):
        post_data['departments'] = ''
        self.c.get(self.locations['login'], self.login_data)
        self.election_form['election_module'] = self.election_type
        self.c.post(self.locations['create'], self.election_form,
                    follow=True)
        Election.objects.all()[0]

    def prepare_trustees(self, e_uuid):
        e = Election.objects.get(uuid=e_uuid)
        pks = {}
        for t in e.trustees.all():
            if not t.secret_key:
                login_url = t.get_login_url()
                self.c.get(self.locations['logout'])
                r = self.c.get(login_url)
                self.assertEqual(r.status_code, 302)
                t1_kp = ELGAMAL_PARAMS.generate_keypair()
                pk = algs.EGPublicKey.from_dict(dict(p=t1_kp.pk.p,
                                                     q=t1_kp.pk.q,
                                                     g=t1_kp.pk.g,
                                                     y=t1_kp.pk.y))
                pok = t1_kp.sk.prove_sk(DLog_challenge_generator)
                post_data = {
                    'public_key_json': [
                        json.dumps({
                            'public_key': pk.toJSONDict(),
                            'pok': {
                                'challenge': pok.challenge,
                                'commitment': pok.commitment,
                                'response': pok.response}
                            })]}

                r = self.c.post('/elections/%s/trustee/upload_pk' %
                               (e_uuid), post_data, follow=True)
                self.assertEqual(r.status_code, 200)
                t = Trustee.objects.get(pk=t.pk)
                t.last_verified_key_at = datetime.datetime.now()
                t.save()
                pks[t.uuid] = t1_kp
        self.verbose('+ Trustees are ready')
        return pks

    def freeze_election(self):
        e = Election.objects.get(uuid=self.e_uuid)
        self.c.get(self.locations['logout'])
        self.c.post(self.locations['login'], self.login_data)
        freeze_location = '/elections/%s/freeze' % self.e_uuid
        self.c.post(freeze_location, follow=True)
        e = Election.objects.get(uuid=self.e_uuid)
        if e.frozen_at:
            self.verbose('+ Election got frozen')
            return True

    def extend_election_voting_end(self):
        self.c.get(self.locations['logout'])
        self.c.post(self.locations['login'], self.login_data)
        r = self.c.get('/elections/{}/edit'.format(self.e_uuid),
                       follow=True)
        form = r.context['form']
        data = form.initial
        # need to split date and hours again for form
        start = data['voting_starts_at']
        end = data['voting_ends_at']
        data['voting_starts_at_0'] = start.strftime('%Y-%m-%d')
        data['voting_starts_at_1'] = start.strftime('%H:%M')
        data['voting_ends_at_0'] = end.strftime('%Y-%m-%d')
        data['voting_ends_at_1'] = end.strftime('%H:%M')

        ext_date = datetime.datetime.now() + timedelta(hours=198)
        data['voting_extended_until_0'] = ext_date.strftime('%Y-%m-%d')
        data['voting_extended_until_1'] = ext_date.strftime('%H:%M')
        r = self.c.post('/elections/{}/edit'.format(self.e_uuid),
                        data,
                        follow=True
                        )
        e = Election.objects.get(uuid=self.e_uuid)
        self.assertNotEqual(e.voting_extended_until, None)

    def create_duplicate_polls(self):
        self.c.get(self.locations['logout'])
        self.c.post(self.locations['login'], self.login_data)
        location = '/elections/%s/polls/add' % self.e_uuid
        post_data = {
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 0,
            'form-MAX_NUM_FORMS': 100
            }
        for i in range(0, 2):
            post_data['form-%s-name' % i] = 'test_poll'
        self.c.post(location, post_data)
        e = Election.objects.all()[0]
        self.assertEqual(e.polls.all().count(), 0)
        self.verbose('- Polls were not created - duplicate poll names')

    def create_polls(self):
        self.c.get(self.locations['logout'])
        self.c.post(self.locations['login'], self.login_data)
        e = Election.objects.all()[0]
        # there shouldn't be any polls before we create them
        self.assertEqual(e.polls.all().count(), 0)
        location = '/elections/%s/polls/add' % self.e_uuid
        post_data = {
            'form-TOTAL_FORMS': self.polls_number,
            'form-INITIAL_FORMS': 0,
            'form-MAX_NUM_FORMS': 100
            }
        for i in range(0, self.polls_number):
            post_data['form-%s-name' % i] = 'test_poll%s' % i

        self.c.post(location, post_data)
        e = Election.objects.all()[0]
        self.assertEqual(e.polls.all().count(), self.polls_number)
        self.verbose('+ Polls were created')
        self.p_uuids = []
        for poll in e.polls.all():
            self.p_uuids.append(poll.uuid)

    def submit_questions(self):
        for p_uuid in self.p_uuids:
            post_data, nr_questions, duplicate_post_data = \
                self.create_questions()
            questions_location = '/elections/%s/polls/%s/questions/manage' % \
                (self.e_uuid, p_uuid)
            resp = self.c.post(questions_location, duplicate_post_data)
            self.assertTrue(resp.context['form'].errors)
            p = Poll.objects.get(uuid=p_uuid)
            self.assertEqual(p.questions_count, 0)
            self.verbose('- Duplicate answers were not allowed in poll %s'
                         % p.name)
            resp = self.c.post(questions_location, post_data)
            self.assertFalse(resp.context)
            p = Poll.objects.get(uuid=p_uuid)
            self.assertEqual(p.questions_count, nr_questions)
        self.verbose('+ Questions were created')

    def submit_duplicate_id_voters_file(self):
        counter = 0
        voter_files = {}
        for p_uuid in self.p_uuids:
            fname = '/tmp/faulty_voters%s.csv' % counter
            voter_files[p_uuid] = fname
            fp = file(fname, 'w')
            for i in range(0, 2):
                voter = "1,voter%s@mail.com,test_name%s,test_surname%s\n" \
                    % (i, i, i)
                fp.write(voter)
            fp.close()
            counter += 1
        self.verbose('- Faulty voters file(duplicate ids) created')
        for p_uuid in self.p_uuids:
            upload_voters_location = '/elections/%s/polls/%s/voters/upload' \
                                     % (self.e_uuid, p_uuid)
            self.c.post(
                upload_voters_location,
                {'voters_file': file(voter_files[p_uuid])}
                )
            self.c.post(upload_voters_location, {'confirm_p': 1})
            e = Election.objects.get(uuid=self.e_uuid)
            nr_voters = e.voters.count()
            self.assertEqual(nr_voters, 0)
        self.verbose('- Voters from faulty file were not submitted')

    def submit_wrong_field_number_voters_file(self):
        counter = 0
        voter_files = {}
        for p_uuid in self.p_uuids:
            fname = '/tmp/wrong_voters%s.csv' % counter
            voter_files[p_uuid] = fname
            fp = file(fname, 'w')
            for i in range(1, self.voters_num+1):
                voter = ("%s,voter%s@mail.com,test_name%s,test_surname%s,"
                         "fname,4444444444,lol\n"
                         % (i, i, i, i))
                fp.write(voter)
            fp.close()
            counter += 1
        self.verbose('+ Faulty voters file(fields>6) created')
        for p_uuid in self.p_uuids:
            upload_voters_location = '/elections/%s/polls/%s/voters/upload' \
                % (self.e_uuid, p_uuid)
            r = self.c.post(
                upload_voters_location,
                {'voters_file': file(voter_files[p_uuid])}
                )
            r = self.c.post(upload_voters_location, {'confirm_p': 1})
            self.assertEqual(r.status_code, 302)
            e = Election.objects.get(uuid=self.e_uuid)
            nr_voters = e.voters.count()
            self.assertEqual(nr_voters, 0)
        self.verbose('- Voters from faulty file were not submitted')

    def get_voters_file(self):
        counter = 0
        voter_files = {}
        for p_uuid in self.p_uuids:
            fname = '/tmp/random_voters%s.csv' % counter
            voter_files[p_uuid] = fname
            fp = file(fname, 'w')
            for i in range(1, self.voters_num+1):
                voter = "%s,voter%s@mail.com,test_name%s,test_surname%s\n" \
                    % (i, i, i, i)
                fp.write(voter)
            fp.close()
            counter += 1
        self.verbose('+ Voters file created')
        return voter_files

    def submit_voters_file(self):
        voter_files = self.get_voters_file()
        for p_uuid in self.p_uuids:
            upload_voters_location = '/elections/%s/polls/%s/voters/upload' \
                % (self.e_uuid, p_uuid)
            self.c.post(
                upload_voters_location,
                {'voters_file': file(voter_files[p_uuid])}
                )
            self.c.post(upload_voters_location, {'confirm_p': 1})
        e = Election.objects.get(uuid=self.e_uuid)
        voters = e.voters.count()
        self.assertEqual(voters, self.voters_num*self.polls_number)
        self.verbose('+ Voters file submitted')

    def get_voters_urls(self):
        # return a dict with p_uuid as key and
        # voters urls as a list for each poll
        voters_urls = {}
        for p_uuid in self.p_uuids:
            urls_for_this_poll = []
            p = Poll.objects.get(uuid=p_uuid)
            voters = p.voters.all()
            for v in voters:
                urls_for_this_poll.append(v.get_quick_login_url())
            voters_urls[p_uuid] = urls_for_this_poll
        self.verbose('+ Got login urls for voters')
        return voters_urls

    def voter_cannot_vote_before_freeze(self):
        voter_login_url = (
            Election.objects
            .get(uuid=self.e_uuid)
            .voters.all()[0]
            .get_quick_login_url())
        p_uuid = self.p_uuids[0]
        r = self.single_voter_cast_ballot(voter_login_url, p_uuid)
        self.assertEqual(r.status_code, 403)
        self.verbose('- Voting  was not allowed - not frozen yet')

    def voter_cannot_vote_after_close(self):
        self.c.get(self.locations['logout'])
        voter_login_url = (
            Election.objects
            .get(uuid=self.e_uuid)
            .voters.all()[0]
            .get_quick_login_url())
        p_uuid = self.p_uuids[0]
        r = self.c.get(voter_login_url, follow=True)
        self.assertTrue(('Η ψηφοφορία έχει λήξει' in r.content)
                        or ('Voting closed' in r.content))
        self.verbose('- Voter trying to vote was informed that'
                     ' voting is closed')
        r = self.c.post('/elections/%s/polls/%s/cast'
                        % (self.e_uuid, p_uuid), {})
        self.assertEqual(r.status_code, 403)
        self.verbose('- Voter cannot access cast vote view after close')

    def submit_vote_for_each_voter(self, voters_urls):
        for p_uuid in voters_urls:
            for voter_url in voters_urls[p_uuid]:
                self.single_voter_cast_ballot(voter_url, p_uuid)
        for p_uuid in self.p_uuids:
            p = Poll.objects.get(uuid=p_uuid)
            self.assertEqual(p.voters_cast_count(), self.voters_num)

    def single_voter_cast_ballot(self, voter_url, p_uuid):
        # make balot returns ballot_data and size
        data = self.make_ballot(p_uuid)
        r = self.encrypt_ballot_and_cast(data[0], data[1], voter_url, p_uuid)
        return r

    def make_ballot(self, p_uuid):
        raise Exception(NotImplemented)

    def encrypt_ballot_and_cast(self, selection, size, the_url, p_uuid):
        self.c.get(self.locations['logout'])
        e = Election.objects.get(uuid=self.e_uuid)
        rel_selection = to_relative_answers(selection, size)
        encoded = gamma_encode(rel_selection, size, size)
        plaintext = algs.EGPlaintext(encoded, e.public_key)
        randomness = algs.Utils.random_mpz_lt(e.public_key.q)
        cipher = e.public_key.encrypt_with_r(plaintext, randomness, True)
        modulus, generator, order = e.zeus.do_get_cryptosystem()
        enc_proof = prove_encryption(modulus, generator, order, cipher.alpha,
                                     cipher.beta, randomness)
        r = self.c.get(the_url, follow=True)
        self.assertEqual(r.status_code, 200)
        cast_data = {}
        ##############
        ballot = {
            'election_hash': 'foobar',
            'election_uuid': e.uuid,
            'answers': [{
                'encryption_proof': enc_proof,
                'choices': [{
                    'alpha': cipher.alpha,
                    'beta': cipher.beta}]
                }]
            }
        ##############
        enc_vote = datatypes.LDObject.fromDict(
            ballot, type_hint='phoebus/EncryptedVote').wrapped_obj
        cast_data['encrypted_vote'] = enc_vote.toJSON()
        r = self.c.post('/elections/%s/polls/%s/cast'
                        % (self.e_uuid, p_uuid), cast_data)
        voter = self.get_voter_from_url(the_url)
        p = Poll.objects.get(uuid=p_uuid)
        self.verbose('+ Voter %s voting at poll %s' % (voter.name, p.name))
        return r

    def close_election(self):
        self.c.get(self.locations['logout'])
        self.c.post(self.locations['login'], self.login_data)
        e = Election.objects.get(uuid=self.e_uuid)
        e.voting_ends_at = datetime.datetime.now()
        e.voting_extended_until = datetime.datetime.now()
        e.save()
        self.c.post('/elections/%s/close' % self.e_uuid)
        e = Election.objects.get(uuid=self.e_uuid)
        self.assertTrue(e.feature_closed)
        self.verbose('+ Election is closed')

    def decrypt_with_trustees(self, pks):
        for trustee, kp in pks.iteritems():
            t = Trustee.objects.get(uuid=trustee)
            self.c.get(self.locations['logout'])
            self.c.get(t.get_login_url())

            sk = kp.sk
            for p_uuid in self.p_uuids:
                p = Poll.objects.get(uuid=p_uuid)
                decryption_factors = [[]]
                decryption_proofs = [[]]
                for vote in p.encrypted_tally.tally[0]:
                    dec_factor, proof = sk.decryption_factor_and_proof(vote)
                    decryption_factors[0].append(dec_factor)
                    decryption_proofs[0].append({
                        'commitment': proof.commitment,
                        'response': proof.response,
                        'challenge': proof.challenge,
                        })
                data = {
                    'decryption_factors': decryption_factors,
                    'decryption_proofs': decryption_proofs
                    }
                location = '/elections/%s/polls/%s/post-decryptions' \
                    % (self.e_uuid, p_uuid)
                post_data = {'factors_and_proofs': json.dumps(data)}
                r = self.c.post(location, post_data)
                self.assertEqual(r.status_code, 200)
                self.verbose('+ Trustee %s decrypted poll %s'
                             % (t.name, p.name))


    def check_cast_votes(self):
        # check validity of sums of cast votes based on voter weights
        for p_uuid in self.p_uuids:
            p = Poll.objects.get(uuid=p_uuid)
            mix_input = p.zeus.extract_votes_for_mixing()[1]
            voter_weights = p.voters.filter().\
                exclude(excluded_at__isnull=False).\
                values_list('voter_weight', flat=True)
            self.assertEqual(sum(voter_weights), len(mix_input))
            self.verbose('+ Valid cast votes sums for poll %s' % p.name)

    def check_results(self):
        # check if results exist
        for p_uuid in self.p_uuids:
            p = Poll.objects.get(uuid=p_uuid)
            self.assertTrue(len(p.result[0]) > 0)
            self.verbose('+ Results generated for poll %s' % p.name)
            self.assertIsNone(p.compute_results_error)


    def check_docs_exist(self, ext_dict):
        e_exts = ext_dict['el']
        p_exts = ext_dict['poll']
        e = Election.objects.get(uuid=self.e_uuid)
        el_module = e.get_module()
        poll_modules = [poll.get_module() for poll in e.polls.all()]
        for lang in settings.LANGUAGES:
            for ext in p_exts:
                for p_module in poll_modules:
                    path = p_module.get_poll_result_file_path(
                        ext,
                        ext,
                        lang[0]
                    )
                    if ext == 'json':
                        path = p_module.get_poll_result_file_path(ext, ext)
                    self.assertTrue(os.path.exists(path))
            for ext in e_exts:
                e_path = el_module.get_election_result_file_path(
                    ext,
                    ext,
                    lang[0]
                )
                self.assertTrue(os.path.exists(e_path))
        self.verbose('+ Docs generated')

    def view_returns_poll_proofs_file(self, client, e_uuid, p_uuid):
        address = '/elections/%s/polls/%s/proofs.zip' % \
            (e_uuid, p_uuid)
        r = client.get(address)
        response_data = dict(r.items())
        self.assertTrue(
            response_data['Content-Type'] == 'application/zip'
            )

    def view_returns_result_files(self, ext_dict):
        p_exts = ext_dict['poll']
        e_exts = ext_dict['el']
        self.c.get(self.locations['logout'])
        self.c.post(self.locations['login'], self.login_data)
        e = Election.objects.get(uuid=self.e_uuid)
        for lang in settings.LANGUAGES:
            for poll in e.polls.all():
                self.view_returns_poll_proofs_file(self.c, e.uuid, poll.uuid)
                for ext in p_exts:
                    if ext is not 'json':
                        address = ('/elections/%s/polls/%s/results-%s.%s'
                                   % (self.e_uuid, poll.uuid, lang[0], ext))
                    else:
                        address = '/elections/%s/polls/%s/results.%s' % \
                            (self.e_uuid, poll.uuid, ext)
                    r = self.c.get(address)
                    response_data = dict(r.items())
                    self.assertTrue(
                        response_data['Content-Type'] == 'application/%s'
                        % ext
                        )
            for ext in e_exts:
                address = '/elections/%s/results/%s-%s.%s' % \
                    (e.uuid, e.short_name, lang[0], ext)
                r = self.c.get(address)
                response_data = dict(r.items())
                self.assertTrue(
                    response_data['Content-Type'] == 'application/%s'
                    % ext
                    )
        self.verbose('+ Requested downloadable content is available')

    def zip_contains_files(self, doc_exts):
        el_exts = doc_exts['el']
        poll_exts = doc_exts['poll']
        el_exts.remove('zip')

        e = Election.objects.get(uuid=self.e_uuid)
        el_module = e.get_module()
        for lang in settings.LANGUAGES:
            all_files_paths = []
            for ext in el_exts:
                    path = el_module.get_election_result_file_path(
                        ext,
                        ext,
                        lang[0]
                        )
                    all_files_paths.append(path)
            for poll in e.polls.all():
                p_module = poll.get_module()
                for ext in poll_exts:
                    if ext is not 'json':
                        path = p_module.get_poll_result_file_path(
                            ext,
                            ext,
                            lang[0]
                            )
                        all_files_paths.append(path)
                    else:
                        path = el_module.get_election_result_file_path(
                            ext,
                            ext
                            )
            file_names = []
            for path in all_files_paths:
                name = os.path.basename(path)
                file_names.append(name)
            zippath = el_module.get_election_result_file_path(
                'zip',
                'zip',
                lang[0]
                )
            zip_file = zipfile.ZipFile(zippath, 'r')
            files_in_zip = zip_file.namelist()
            for file_name in file_names:
                self.assertTrue(bool(file_name in files_in_zip))
            self.verbose('+ Zip in %s contains all docs' % lang[1])

    def first_trustee_step_and_admin_mail(self):
        trustees = Election.objects.get(uuid=self.e_uuid).trustees.all()
        admins = settings.ADMINS
        # 1 zeus trustee, does not get mail
        # 1 mail to admins with all addresses
        mail_num = len(trustees)
        self.assertEqual(len(mail.outbox), mail_num)

        for email in mail.outbox:
            for admin in admins:
                if admin[1] in email.to:
                    prefix = settings.EMAIL_SUBJECT_PREFIX
                    message = u'New Zeus election'
                    self.assertEqual(email.subject, prefix+message)
            for trustee in trustees:
                if trustee.email in email.to[0]:
                    self.assertTrue(u'step #1' in email.subject)
        mail.outbox = []

    def second_trustee_step_mail(self):
        # admin did not get any mail yet
        # trustees got mail for step 2
        trustees = Election.objects.get(uuid=self.e_uuid).trustees.all()
        mail_num = len(trustees) - 1
        self.assertEqual(len(mail.outbox), mail_num)
        for email in mail.outbox:
            for trustee in trustees:
                if trustee.email in email.to[0]:
                    self.assertTrue(u'step #2' in email.subject)
        mail.outbox = []

    def admin_notified_for_freeze(self):
        admins = settings.ADMINS
        # 1 mail is sent with multiple addresses in mail.to
        self.assertEqual(len(mail.outbox), 1)
        for email in mail.outbox:
            for admin in admins:
                if admin[1] in email.to:
                    prefix = settings.EMAIL_SUBJECT_PREFIX
                    message = u'Election is frozen'
                    self.assertEqual(email.subject, prefix+message)
        mail.outbox = []

    def admin_notified_for_extension(self):
        admins = settings.ADMINS
        # 1 mail is sent with multiple addresses in mail.to
        self.assertEqual(len(mail.outbox), 1)
        for email in mail.outbox:
            for admin in admins:
                if admin[1] in email.to:
                    prefix = settings.EMAIL_SUBJECT_PREFIX
                    message = u'Voting extension'
                    self.assertEqual(email.subject, prefix+message)
        mail.outbox = []

    def voters_received_voting_receipt(self):
        voters = Election.objects.get(uuid=self.e_uuid).voters.all()
        self.assertEqual(len(mail.outbox), len(voters))
        for email in mail.outbox:
            for voter in voters:
                if voter.voter_email in email.to[0]:
                    self.assertTrue(u'vote cast' in email.subject)
        mail.outbox = []

    def emails_after_election_close(self):
        # admin mails that must be sent:
        # election closed - validate voting finished
        # mixing finished - validate mixing finished - 4 in total
        # mail to trustee for step 3
        trustees = Election.objects.get(uuid=self.e_uuid).trustees.all()
        admins = settings.ADMINS
        # remove zeus trustee, does not get mail
        mail_num = len(trustees) + 3  # -1 zeus trustee + 4 to admins
        self.assertEqual(len(mail.outbox), mail_num)
        admin_messages = [
            'Election closed',
            'Validate voting finished',
            'Mixing finished',
            'Validate mixing finished',
            ]
        prefix = settings.EMAIL_SUBJECT_PREFIX
        admin_messages = [prefix + s for s in admin_messages]
        for email in mail.outbox:
            for admin in admins:
                if admin[1] in email.to[0]:
                    self.assertTrue(email.subject in admin_messages)
            for trustee in trustees:
                if trustee.email in email.to[0]:
                    self.assertTrue(u'step #3' in email.subject)
        mail.outbox = []

    def decryption_and_result_admin_mails(self):
        # at this step admins get emails for
        # trustees partial decryptions finished
        # decryption finished
        # results computed - docs generated - 3 mails in total
        admins = settings.ADMINS
        mail_num = 3
        self.assertEqual(len(mail.outbox), mail_num)
        admin_messages = [
            'Trustees partial decryptions finished',
            'Decryption finished',
            'Results computed - docs generated',
            ]
        prefix = settings.EMAIL_SUBJECT_PREFIX
        admin_messages = [prefix + s for s in admin_messages]
        for email in mail.outbox:
            for admin in admins:
                if admin[1] in email.to[0]:
                    self.assertTrue(email.subject in admin_messages)
        mail.outbox = []

    def election_process(self):
        self.election_form_with_wrong_dates()
        self.admin_can_submit_election_form()
        self.first_trustee_step_and_admin_mail()
        e = Election.objects.get(uuid=self.e_uuid)
        self.assertEqual(self.freeze_election(), None)
        pks = self.prepare_trustees(self.e_uuid)
        self.second_trustee_step_mail()
        self.create_duplicate_polls()
        self.create_polls()
        self.submit_duplicate_id_voters_file()
        self.submit_wrong_field_number_voters_file()
        self.submit_voters_file()
        self.submit_questions()
        self.voter_cannot_vote_before_freeze()
        e = Election.objects.get(uuid=self.e_uuid)
        self.assertEqual(e.election_issues_before_freeze, [])
        self.assertTrue(self.freeze_election())
        self.admin_notified_for_freeze()
        e = Election.objects.get(uuid=self.e_uuid)
        e.voting_starts_at = datetime.datetime.now()
        e.save()
        voters_urls = self.get_voters_urls()
        self.extend_election_voting_end()
        self.admin_notified_for_extension()
        self.submit_vote_for_each_voter(voters_urls)
        self.voters_received_voting_receipt()
        self.close_election()
        self.emails_after_election_close()
        self.voter_cannot_vote_after_close()
        e = Election.objects.get(uuid=self.e_uuid)
        self.assertTrue(e.feature_mixing_finished)
        self.decrypt_with_trustees(pks)
        self.decryption_and_result_admin_mails()
        self.check_cast_votes()
        self.check_results()
        self.check_docs_exist(self.doc_exts)
        self.view_returns_result_files(self.doc_exts)
        self.zip_contains_files(self.doc_exts)
        if self.local_verbose:
            print self.celebration

    def broken_mix_election_process(self):
        self.admin_can_submit_election_form()
        self.first_trustee_step_and_admin_mail()
        e = Election.objects.get(uuid=self.e_uuid)
        self.assertEqual(self.freeze_election(), None)
        self.prepare_trustees(self.e_uuid)
        self.second_trustee_step_mail()
        self.create_polls()
        self.submit_voters_file()
        self.submit_questions()
        e = Election.objects.get(uuid=self.e_uuid)
        self.assertTrue(self.freeze_election())
        self.admin_notified_for_freeze()
        e = Election.objects.get(uuid=self.e_uuid)
        e.voting_starts_at = datetime.datetime.now()
        e.save()
        voters_urls = self.get_voters_urls()
        self.submit_vote_for_each_voter(voters_urls)
        self.voters_received_voting_receipt()
        self.close_election()


class TestSimpleElection(TestElectionBase):

    def setUp(self):
        self.doc_exts = {
            'poll': ['pdf', 'csv', 'json'],
            'el': ['pdf', 'csv', 'zip']
            }
        super(TestSimpleElection, self).setUp()
        self.election_type = 'simple'
        if self.local_verbose:
            print '* Starting simple election *'

    def create_questions(self):
        max_nr_questions = self.simple_election_max_questions_number
        max_nr_answers = self.simple_election_max_answers_number
        nr_questions = randint(1, max_nr_questions)

        post_data = {
            'form-TOTAL_FORMS': nr_questions,
            'form-INITIAL_FORMS': 1,
            'form-MAX_NUM_FORMS': "",
            }

        post_data_with_duplicate_answers = post_data.copy()

        for num in range(0, nr_questions):
            nr_answers = randint(1, max_nr_answers)
            min_choices = randint(1, nr_answers)
            max_choices = randint(min_choices, nr_answers)
            duplicate_extra_data = {}
            extra_data = {}
            extra_data = {
                'form-%s-ORDER' % num: num,
                'form-%s-choice_type' % num: 'choice',
                'form-%s-question' % num: 'test_question_%s' % num,
                'form-%s-min_answers' % num: min_choices,
                'form-%s-max_answers' % num: max_choices,
                }
            duplicate_extra_data = extra_data.copy()
            for ans_num in range(0, nr_answers):
                extra_data['form-%s-answer_%s' % (num, ans_num)] = \
                    'test answer %s' % ans_num
                duplicate_extra_data['form-%s-answer_%s' % (num, ans_num)] = \
                    'test answer 0'
                #make sure we have at least 2 answers so there can be duplicate
                duplicate_extra_data['form-%s-answer_%s' % (num, ans_num+1)] =\
                    'test answer 0'
            post_data_with_duplicate_answers.update(duplicate_extra_data)
            post_data.update(extra_data)
        return post_data, nr_questions, post_data_with_duplicate_answers

    def make_ballot(self, p_uuid):
        poll = Poll.objects.get(uuid=p_uuid)
        q_d = poll.questions_data
        max_choices = len(poll.questions[0]['answers'])
        choices = []
        index = 1
        vote_blank = randint(0, 4)
        for qindex, data in enumerate(q_d):
            if vote_blank == 0:
                break
            # valid answer indexes
            valid_indexes = range(index, index + (len(data['answers'])))
            min, max = int(data['min_answers']), int(data['max_answers'])
            qchoice = []
            nr_choices = randint(min, max)
            qchoice = sample(valid_indexes, nr_choices)
            '''
            while len(qchoice) < random.randint(min, max):
                answer = random.choice(valid_indexes)
                valid_indexes.remove(answer)
                qchoice.append(answer)
            '''
            qchoice = sorted(qchoice)
            choices += qchoice
            # inc index to the next question
            index += len(data['answers']) + 1
        return choices, max_choices

    def test_election_process(self):
        self.election_process()

    def test_broken_mix_election_process(self):

        from zeus.model_tasks import poll_task, PollTasks
        raised_error = 'Intended error'

        @poll_task('mix', ('validate_voting_finished',), completed_cb=None)
        def mix(self, remote=None):
            raise Exception(raised_error)
        orig = PollTasks.mix
        PollTasks.mix = mix
        self.broken_mix_election_process()
        PollTasks.mix = orig
        admins = settings.ADMINS
        prefix = settings.EMAIL_SUBJECT_PREFIX
        admin_messages = [
            'Election closed',
            'Validate voting finished',
            'Task mix error, {}'.format(raised_error),
            raised_error,
            ]
        admin_messages = [prefix + s for s in admin_messages]
        for email in mail.outbox:
            for admin in admins:
                if admin[1] in email.to[0]:
                    self.assertTrue(email.subject in admin_messages)


class TestPartyElection(TestElectionBase):

    def setUp(self):
        super(TestPartyElection, self).setUp()
        self.election_type = 'parties'
        self.doc_exts = {
            'poll': ['pdf', 'csv', 'json'],
            'el': ['pdf', 'csv', 'zip']
            }
        if self.local_verbose:
            print '* Starting party election *'

    def create_questions(self):
        nr_questions = self.party_election_max_questions_number
        max_nr_answers = self.party_election_max_answers_number

        post_data = {'form-TOTAL_FORMS': nr_questions,
                     'form-INITIAL_FORMS': 1,
                     'form-MAX_NUM_FORMS': ""
                     }
        post_data_with_duplicate_answers = post_data.copy()

        for num in range(0, nr_questions):
            nr_answers = randint(1, max_nr_answers)
            min_choices = randint(1, nr_answers)
            max_choices = randint(min_choices, nr_answers)
            extra_data = {}
            extra_data = {
                'form-%s-ORDER' % num: num,
                'form-%s-choice_type' % num: 'choice',
                'form-%s-question' % num: 'test question %s' % num,
                'form-%s-min_answers' % num: min_choices,
                'form-%s-max_answers' % num: max_choices,
                }
            duplicate_extra_data = extra_data.copy()
            for ans_num in range(0, nr_answers):
                extra_data['form-%s-answer_%s' % (num, ans_num)] = \
                    'testanswer %s-%s' % (num, ans_num)
                duplicate_extra_data['form-%s-answer_%s' % (num, ans_num)] = \
                    'testanswer 0-0'
                ans_num += 1
                duplicate_extra_data['form-%s-answer_%s' % (num, ans_num)] = \
                    'testanswer 0-0'
            post_data_with_duplicate_answers.update(duplicate_extra_data)
            post_data.update(extra_data)
        return post_data, nr_questions, post_data_with_duplicate_answers

    def make_ballot(self, p_uuid):
        poll = Poll.objects.get(uuid=p_uuid)
        q_d = poll.questions_data
        max_choices = len(poll.questions[0]['answers'])
        choices = []
        header_index = 0
        index = 1
        # if vote_blank is 0, the selection will be empty
        vote_blank = randint(0, 4)
        for qindex, data in enumerate(q_d):
            if vote_blank == 0:
                break
            qchoice = []
            # if vote party only is 0, vote only party without candidates
            vote_party_only = randint(0, 4)
            if vote_party_only == 0:
                qchoice.append(header_index)
            else:
                # valid answer indexes
                valid_indexes = range(index, index + (len(data['answers'])))
                min, max = int(data['min_answers']), int(data['max_answers'])
                nr_choices = randint(min, max)
                qchoice = sample(valid_indexes, nr_choices)
                '''
                while len(qchoice) < random.randint(min, max):
                    answer = random.choice(valid_indexes)
                    valid_indexes.remove(answer)
                    qchoice.append(answer)
                '''
            qchoice = sorted(qchoice)
            choices += qchoice
            # inc index to the next question
            index += len(data['answers']) + 1
            header_index += len(data['answers']) + 1
        return choices, max_choices

    def test_election_process(self):
        self.election_process()


# used for creating score elections ballot
def make_random_range_ballot(candidates_to_index, scores_to_index):

    candidate_indexes = candidates_to_index.values()
    score_indexes = scores_to_index.values()
    nr_scores = len(score_indexes)
    nr_candidates = len(candidate_indexes)
    max_nr_choices = min(nr_candidates, nr_scores)

    selected_score_indexes = \
        sample(score_indexes, randint(0, max_nr_choices))
    selected_score_indexes.sort()
    selected_candidate_indexes = sample(
        candidate_indexes,
        len(selected_score_indexes)
        )
    shuffle(selected_candidate_indexes)
    ballot_choices = izip(selected_candidate_indexes, selected_score_indexes)
    ballot_choices = chain(*ballot_choices)
    ballot_choices = list(ballot_choices)
    max_ballot_choices = nr_scores + nr_candidates

    return ballot_choices, max_ballot_choices


class TestScoreElection(TestElectionBase):

    def setUp(self):
        super(TestScoreElection, self).setUp()
        self.doc_exts = {
            'poll': ['csv', 'json'],
            'el': ['csv', 'zip']
            }
        self.election_type = 'score'
        if self.local_verbose:
            print '* Starting score election *'

    min_answers = None
    max_answers = None
    max_answers_limit = 9

    def create_questions(self):
        # var bellow is not used, should it?
        # max_nr_answers = self.score_election_max_answers
        nr_answers = randint(1, self.max_answers_limit)
        available_scores = [x for x in range(1, 10)]
        scores_list = sample(available_scores, nr_answers)
        scores_list.sort()

        min_answers = len(scores_list)
        max_answers = len(scores_list)

        if self.min_answers is not None:
            min_answers = self.min_answers
        if self.max_answers is not None:
            max_answers = self.max_answers

        post_data = {'form-TOTAL_FORMS': 1,
                     'form-INITIAL_FORMS': 1,
                     'form-MAX_NUM_FORMS': "",
                     'form-0-choice_type': 'choice',
                     'form-0-scores': scores_list,
                     'form-0-question': 'test_question',
                     'form-0-max_answers': max_answers,
                     'form-0-min_answers': min_answers
                     }
        post_data_with_duplicate_answers = post_data.copy()
        extra_data = {}
        duplicate_extra_data = {}

        for num in range(0, nr_answers):
            extra_data['form-0-answer_%s' % num] = 'test answer %s' % num
            duplicate_extra_data['form-0-answer_%s' % num] = 'test answer 0'
            duplicate_extra_data['form-0-answer_%s' % (num+1)] = \
                'test answer 0'
        post_data_with_duplicate_answers.update(duplicate_extra_data)
        post_data.update(extra_data)
        # 1 is the number of questions, used for assertion
        return post_data, 1, post_data_with_duplicate_answers

    def make_ballot(self, p_uuid):
        p = Poll.objects.get(uuid=p_uuid)
        q_data = p.questions_data[0]
        candidates_to_indexes = q_data['answer_indexes']
        scores_to_indexes = q_data['score_indexes']
        ballot_choices, max_ballot_choices = make_random_range_ballot(
            candidates_to_indexes, scores_to_indexes)
        return ballot_choices, max_ballot_choices

    def test_election_process(self):
        self.election_process()


class TestSTVElection(TestElectionBase):

    def setUp(self):
        super(TestSTVElection, self).setUp()
        self.election_type = 'stv'
        self.doc_exts = {
            'poll': ['pdf', 'csv', 'json'],
            'el': ['pdf', 'csv', 'zip']
            }
        # make departments for stv election
        departments = ''
        for i in range(0, randint(2, 10)):
            departments += 'test department %s\n' % i
        self.departments = departments
        if self.local_verbose:
            print '* Starting stv election *'

    def create_questions(self):

        nr_candidates = randint(2, self.stv_election_max_answers_number)
        eligibles = randint(1, nr_candidates)
        # choose randomly if has department limit
        post_data = {
            'form-MAX_NUM_FORMS': 1000,
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-ORDER': 1,
            'form-0-eligibles': eligibles,
            }
        post_data_with_duplicate_answers = post_data.copy()
        e = Election.objects.get(uuid=self.e_uuid)
        departments = e.departments.split('\n')
        extra_data = {}
        duplicate_extra_data = {}

        for i in range(0, nr_candidates):
            extra_data['form-0-answer_%s_0' % i] = 'test candidate %s' % i
            dep_choice = choice(departments)
            extra_data['form-0-answer_%s_1' % i] = dep_choice
            duplicate_extra_data['form-0-answer_%s_0' % i] = \
                'test candidate 0'
            duplicate_extra_data['form-0-answer_%s_1' % i] = dep_choice
            duplicate_extra_data['form-0-answer_%s_0' % (i+1)] = \
                'test candidate 0'
            duplicate_extra_data['form-0-answer_%s_1' % (i+1)] = dep_choice
        # randomize department limit, if 0, has limit
        limit = randint(0, 4)
        if limit == 0:
            post_data['form-0-has_department_limit'] = 'on'
            post_data['form-0-department_limit'] = 2
        post_data_with_duplicate_answers.update(duplicate_extra_data)
        post_data.update(extra_data)
        # 1 is the number of max questions, used for assertion
        return post_data, 1, post_data_with_duplicate_answers

    def make_ballot(self, p_uuid):
        p = Poll.objects.get(uuid=p_uuid)
        nr_candidates = len(p.questions[0]['answers'])
        indexed_candidates = [x for x in range(0, nr_candidates)]
        nr_selection = randint(0, nr_candidates)
        selection = sample(indexed_candidates, nr_selection)

        return selection, nr_candidates

    def test_election_process(self):
        self.election_process()


class TestWeightElection(TestSimpleElection):

    def get_voters_file(self):
        counter = 0
        voter_files = {}
        for p_uuid in self.p_uuids:
            fname = '/tmp/random_voters%s.csv' % counter
            voter_files[p_uuid] = fname
            fp = file(fname, 'w')
            for i in range(1, self.voters_num+1):
                weight = 1 + (i % 5)
                voter = "%s,voter%s@mail.com,test_name%s,test_surname%s,,,%s\n" \
                    % (i, i, i, i, weight)
                fp.write(voter)
            fp.close()
            counter += 1
        self.verbose('+ Voters file created')
        return voter_files
