# -*- coding: utf-8 -*-
import csv

from cStringIO import StringIO
from helios.models import *
from collections import defaultdict
from zeus.core import gamma_decode
from django.db.models import Count
from django.utils.translation import ugettext as _

try:
  from collections import OrderedDict
except ImportError:
  from django.utils.datastructures import SortedDict as OrderedDict

def zeus_report(elections):
    return {
        'elections': elections,
        'votes': CastVote.objects.filter(election__in=elections, voter__excluded_at__isnull=True).count(),
        'voters': Voter.objects.filter(election__in=elections).count(),
        'voters_cast': CastVote.objects.filter(election__in=elections,
                                         voter__excluded_at__isnull=True).distinct('voter').count()
    }


SENSITIVE_DATA = ['admin_user', 'trustees', 'last_view_at']

def election_report(elections, votes_report=True, filter_sensitive=True):
    for e in elections:
        entry = OrderedDict([
            ('name', e.name),
            ('uuid', e.uuid),
            ('admin_user', e.admins.filter().values('user_id',
                                                        'ecounting_account')[0]),
            ('institution', e.institution.name),
            ('voting_started_at', e.voting_starts_at),
            ('voting_ended_at', e.voting_ended_at),
            ('voting_extended', bool(e.voting_extended_until)),
            ('voting_extended_until', e.voting_extended_until),
            ('voting_ends_at', e.voting_ends_at),
            ('trustees', list(e.trustees.filter().no_secret().values('name', 'email'))),
        ])
        if votes_report:
            voters_added = e.voters.count()
            entry.update(OrderedDict([
                ('excluded_count', e.voters.filter(excluded_at__isnull=False).count()),
                ('audit_requests_count', e.audits.filter().requests().count()),
                ('audit_cast_count', e.audits.filter().confirmed().count()),
                ('voters_count', e.voters.count()),
                ('voters_cast_count', e.casts.filter().countable().distinct('voter').count()),
                ('excluded_voters_cast_count', e.casts.filter().excluded().distinct('voter').count()),
                ('cast_count', e.casts.count()),
                ('voters_visited_count', e.voters.filter().visited().count()),
                ('last_view_at', e.voters.order_by('-last_visit')[0].last_visit if voters_added else None)
            ]))

        if filter_sensitive:
          for key in [k for k in entry if k in SENSITIVE_DATA]:
            del entry[key]

        yield entry


def election_votes_report(elections, include_alias=False, filter_sensitive=True):
    from helios.models import CastVote
    for vote in CastVote.objects.filter(poll__election__in=elections,
                                    voter__excluded_at__isnull=True).values('voter__alias','voter',
                                                                           'cast_at').order_by('-cast_at'):
        entry = OrderedDict([
        ])
        if include_alias:
            entry['name'] = vote['voter__alias'],
        if not filter_sensitive:
            entry['name'] = Voter.objects.get(pk=vote['voter']).full_name
        if len(elections) > 1:
            entry['poll'] = vote.poll.name

        entry['date'] = vote['cast_at']
        yield entry


def election_voters_report(elections):
    for voter in Voter.objects.filter(poll__election__in=elections,
                                      excluded_at__isnull=True).annotate(cast_count=Count('cast_votes')).order_by('voter_surname'):
        entry = OrderedDict([
            ('name', voter.voter_name),
            ('surname', voter.voter_surname),
            ('fathername', voter.voter_fathername),
            ('email', voter.voter_email),
            ('visited', bool(voter.last_visit)),
            ('votes_count', voter.cast_count)
        ])
        if len(elections) > 1:
            entry['election'] = vote.election.name
        yield entry


def _single_votes(results, clen):
    return filter(lambda sel: len(gamma_decode(sel, clen)) == 1, results)


def _get_choices_sums(results, choices_len):
    data = OrderedDict()
    for i in range(choices_len+1):
        data[str(i)] = 0

    for encoded in results:
        chosen_len = len(gamma_decode(encoded, choices_len))
        data[str(chosen_len)] = data[str(chosen_len)] + 1

    return data


def election_results_report(elections):
    for election in elections:
        for poll in election.polls.all():
            if not poll.result:
                entry = {}
            else:
                entry = OrderedDict([
                    ('choices', len(poll.questions[0]['answers'])),
                    ('protest_votes_count', poll.result[0].count(0)),
                    ('total_count', len(poll.result[0])),
                    ('choices_sums', _get_choices_sums(poll.result[0],
                                                       len(poll.questions[0]['answers'])))
                ])
            if len(elections) > 1:
                entry['election'] = vote.election.name
                entry['poll'] = vote.poll.election.name
        yield entry

def strforce(thing, encoding='utf8'):
    if isinstance(thing, unicode):
        return thing.encode(encoding)
    return str(thing)

def uwriterow(uni_string, csvout):
    string = strforce(uni_string)
    write

def csv_from_polls(election, polls, lang, outfile=None):
    with translation.override(lang):
        if outfile is None:
            outfile = StringIO()
        csvout = csv.writer(outfile, dialect='excel', delimiter=',')
        writerow = csvout.writerow
        # election details
        DATE_FMT = "%d/%m/%Y %H:%S"
        voting_start = _('Start: %s') % (election.voting_starts_at.strftime(DATE_FMT))
        voting_end = _('End: %s') % (election.voting_ends_at.strftime(DATE_FMT))
        extended_until = ""
        if election.voting_extended_until:
            extended_until = _('Extension: %s') % \
                (election.voting_extended_until.strftime(DATE_FMT))

        writerow([strforce(election.name)])
        writerow([strforce(election.institution.name)])
        writerow([strforce(voting_start)])
        writerow([strforce(voting_end)])

        if extended_until:
            writerow([strforce(extended_until)])
        writerow([])

        for poll in polls:
            party_results = poll.zeus.get_results()
            invalid_count = party_results['invalid_count']
            blank_count = party_results['blank_count']
            ballot_count = party_results['ballot_count']

            writerow([])
            writerow([])
            writerow([])
            writerow([strforce(poll.name)])
            writerow([])
            writerow([])
            writerow([strforce(_('RESULTS'))])
            writerow([strforce(_('TOTAL VOTES')), strforce(ballot_count)])
            writerow([strforce(_('VALID VOTES')), strforce(ballot_count - invalid_count)])
            writerow([strforce(_('INVALID VOTES')), strforce(invalid_count)])
            writerow([strforce(_('BLANK VOTES')), strforce(blank_count)])

            writerow([])
            writerow([strforce(_('PARTY RESULTS'))])
            party_counters = party_results['party_counts']
            for count, party in party_results['party_counts']:
                if party is None:
                    continue
                party = party.replace("{newline}", " ")
                writerow([strforce(party), strforce(count)])

            writerow([])
            writerow([strforce(_('CANDIDATE RESULTS'))])
            for count, candidate in party_results['candidate_counts']:
                writerow([strforce(candidate), strforce(count)])

            writerow([])
            writerow([strforce(_('BALLOTS'))])
            writerow([strforce(_('ID')), strforce(_('PARTY')),\
                strforce(_('CANDIDATE')), strforce(_('VALID/INVALID/BLANK'))])
            counter = 0
            valid = strforce(_('VALID'))
            invalid = strforce(_('INVALID'))
            blank = strforce(_('BLANK'))
            empty = '---'
            for ballot in party_results['ballots']:
                party = empty
                counter += 1
                if not ballot['valid']:
                    writerow([counter, empty, empty, invalid])
                    continue
                ballot_parties = ballot['parties']
                if not ballot_parties:
                    writerow([counter, empty, empty, blank])
                else:
                    for party in ballot_parties:
                        if party is None:
                            writerow([counter, empty, empty, empty])
                            continue
                        else:
                            party = strforce(party)

                candidates = ballot['candidates']
                if not candidates:
                    writerow([counter, party, empty, valid])
                    continue

                for candidate in candidates:
                    writerow([counter, party, strforce(": ".join(candidate)), valid])

        try:
            outfile.seek(0)
            return outfile.read()
        except:
            return None

def csv_from_stv_polls(election, polls, lang, outfile=None):
    with translation.override(lang):
        if outfile is None:
            outfile = StringIO()
        csvout = csv.writer(outfile, dialect='excel', delimiter=',')
        writerow = csvout.writerow
        
        # election details
        DATE_FMT = "%d/%m/%Y %H:%S"
        voting_start = _('Start: %s') % (election.voting_starts_at.strftime(DATE_FMT))
        voting_end = _('End: %s') % (election.voting_ends_at.strftime(DATE_FMT))
        extended_until = ""
        if election.voting_extended_until:
            extended_until = _('Extension: %s') % \
                (election.voting_extended_until.strftime(DATE_FMT))

        writerow([strforce(election.name)])
        writerow([strforce(election.institution.name)])
        writerow([strforce(voting_start)])
        writerow([strforce(voting_end)])

        if extended_until:
            writerow([strforce(extended_until)])
        writerow([])
        # until here write election name, date etc...
        actions_desc = {
            'elect': _('Elect'),
            'eliminate': _('Eliminated'),
            'quota': _('Eliminated due to quota restriction')}
        from stv.parser import STVParser
        for poll in polls:
            writerow([])
            writerow([strforce(poll.name)])
            writerow([])
            questions = poll.questions
            indexed_cands = {}
            counter = 0
            for item in questions[0]['answers']:
                indexed_cands[str(counter)] = item
                counter += 1

            results_winners = poll.stv_results[0]
            results_all = poll.stv_results[1]
            result_steps = poll.stv_results[2] 
            stv = STVParser(result_steps)
            rounds = list(stv.rounds())
            writerow([])
            writerow([strforce(_("Elected")), strforce(_("Departments"))])
            for winner_data in results_winners:
                 winner_id = winner_data[0]
                 winner = indexed_cands[str(winner_id)]
                 winner = winner.split(':')
                 winner_name = winner[0]
                 winner_department = winner[1]
                 writerow([strforce(winner_name), strforce(winner_department)])
            for num, round in rounds:
                round_name = _('Round ')
                round_name +=str(num)
                writerow([])
                writerow([strforce(round_name)])
                writerow([strforce(_('Candidate')), strforce(_('Votes')),\
                    strforce(_('Draw')), strforce(_('Action'))])
                for name, cand in round['candidates'].iteritems():
                    actions = map(lambda x: x[0], cand['actions'])
                    actions = map(lambda x: x[0], cand['actions'])
                    draw = _("NO")
                    if 'random' in actions:
                        draw = _("YES")
                    action = None
                    if len(actions):
                        action = actions_desc.get(actions[-1])
                    votes = cand['votes']  
                    cand_name = indexed_cands[str(name)]
                    cand_name = cand_name.split(':')[0]
                    writerow([strforce(cand_name),strforce(votes),\
                    strforce(draw), strforce(action)])



def csv_from_score_polls(election, polls, lang, outfile=None):
    with translation.override(lang):
        if outfile is None:
            outfile = StringIO()
        csvout = csv.writer(outfile, dialect='excel', delimiter=',')
        writerow = csvout.writerow
        # election details
        DATE_FMT = "%d/%m/%Y %H:%S"
        voting_start = _('Start: %s') % (election.voting_starts_at.strftime(DATE_FMT))
        voting_end = _('End: %s') % (election.voting_ends_at.strftime(DATE_FMT))
        extended_until = ""
        if election.voting_extended_until:
            extended_until = _('Extension: %s') % \
                (election.voting_extended_until.strftime(DATE_FMT))

        writerow([strforce(election.name)])
        writerow([strforce(election.institution.name)])
        writerow([strforce(voting_start)])
        writerow([strforce(voting_end)])

        if extended_until:
            writerow([strforce(extended_until)])
        writerow([])

        for poll in polls:
            score_results = poll.zeus.get_results()
            invalid_count = len([b for b in score_results['ballots']
                                if b['valid'] == False])
            blank_count = len([b for b in score_results['ballots']
                            if not b.get('candidates')])
            ballot_count = len(score_results['ballots'])

            writerow([])
            writerow([])
            writerow([])
            writerow([strforce(poll.name)])
            writerow([])
            writerow([])
            writerow([strforce(_('RESULTS'))])
            writerow([strforce(_('TOTAL VOTES')), strforce(ballot_count)])
            writerow([strforce(_('VALID VOTES')), strforce(ballot_count - invalid_count)])
            writerow([strforce(_('INVALID VOTES')), strforce(invalid_count)])
            writerow([strforce(_('BLANK VOTES')), strforce(blank_count)])

            writerow([])
            writerow([strforce(_('RANKING'))])
            for score, candidate in sorted(score_results['totals']):
                candidate = candidate.replace("{newline}", " ")
                writerow([strforce(score), strforce(candidate)])

            writerow([])
            writerow([strforce(_('SCORES'))])
            pointlist = list(sorted(score_results['points']))
            pointlist.reverse()
            writerow([strforce(_('CANDIDATE')), strforce(_('SCORES:'))] + pointlist)
            for candidate, points in sorted(score_results['detailed'].iteritems()):
                writerow([strforce(candidate), ''] +
                        [strforce(points[p]) for p in pointlist])

            writerow([])
            writerow([strforce(_('BALLOTS'))])
            writerow([strforce(_('ID')), strforce(_('CANDIDATE')),\
                strforce(_('SCORES')), strforce(_('VALID/INVALID/BLANK'))])
            counter = 0
            valid = strforce(_('VALID'))
            invalid = strforce(_('INVALID'))
            blank = strforce(_('BLANK'))
            empty = '---'
            for ballot in score_results['ballots']:
                counter += 1
                if not ballot['valid']:
                    writerow([counter, empty, empty, invalid])
                    continue
                points = sorted(ballot['candidates'].iteritems())
                for candidate, score in points:
                    candidate = candidate.replace("{newline}", " ")
                    writerow([strforce(counter), strforce(candidate),
                            strforce(score), valid])
        try:
            outfile.seek(0)
            return outfile.read()
        except:
            return None
