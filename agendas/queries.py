from django.db import connection, transaction
from django.core.cache import cache

from itertools import groupby
from operator import itemgetter

import time,datetime

def getAllAgendaPartyVotes(fromdate=None,todate=None):
    results = None
    isFullQuery = (fromdate is None) and (todate is None)
    if isFullQuery:
        results = cache.get('AllAgendaPartyVotes')
    if not results:
        try:
            if fromdate is None:
                fromdate = 0
            fromdt = datetime.datetime.utcfromtimestamp(float(fromdate))
        except ValueError:
            fromdt = datetime.datetime.utcfromtimestamp(float(0))
        try:
            if todate is None:
                todate = time.time()
            todt = datetime.datetime.utcfromtimestamp(float(todate))
        except ValueError:
            todt = datetime.datetime.utcfromtimestamp(float(time.time()))          
        cursor = connection.cursor()
        cursor.execute(PARTY_QUERY,[fromdt,todt,fromdt,todt])
        results = dict(map(lambda (key,group):(key,map(lambda g:(g[1],float(g[2]),float(g[3])),list(group))),
                           groupby(cursor.fetchall(),key=itemgetter(0))))
        if (not fromdate is None) and (not todate is None):
            cache.set('AllAgendaPartyVotes', results, 1800)
    return results

PARTY_QUERY = """
SELECT a.agendaid,
       a.partyid,
       round(coalesce(cast(coalesce(v.totalvotevalue,0.0)/a.totalscore*100.0 as numeric),0.0),2) score,
       round(coalesce(cast(coalesce(v.numvotes,0.0)/a.totalvolume*100.0 as numeric),0.0),2) volume
FROM   (SELECT agid                   agendaid,
               m.id                   partyid,
               sc * m.number_of_seats totalscore,
               numvotes * m.number_of_seats totalvolume
        FROM   (SELECT a.agenda_id               agid,
                       SUM(abs(a.score * a.importance)) sc,
                       COUNT(*) numvotes
                FROM   agendas_agendavote a
                JOIN   laws_vote v
                  ON   a.vote_id = v.id
               WHERE   v.time BETWEEN %s and %s
                GROUP  BY a.agenda_id) agendavalues
               left outer join mks_party m
                 on 1=1) a
       left outer join (SELECT agenda_id, 
                          partyid, 
                          SUM(forvotes) - SUM(againstvotes) totalvotevalue ,
                          SUM(numvotes) numvotes
                   FROM   (SELECT a.agenda_id, 
                                  p.partyid, 
                                  CASE p.vtype 
                                    WHEN 'for' THEN p.numvotes * a.VALUE 
                                    ELSE 0 
                                  END forvotes, 
                                  CASE p.vtype 
                                    WHEN 'against' THEN p.numvotes * a.VALUE 
                                    ELSE 0 
                                  END againstvotes,
                                  p.numvotes numvotes
                           FROM   (SELECT m.current_party_id      partyid, 
                                          v.vote_id voteid, 
                                          v.TYPE    vtype, 
                                          COUNT(*)  numvotes 
                                   FROM   laws_voteaction v 
                                          inner join mks_member m 
                                            ON v.member_id = m.id 
                                   WHERE  v.TYPE IN ( 'for', 'against' ) 
                                   GROUP  BY m.current_party_id, 
                                             v.vote_id, 
                                             v.TYPE) p 
                                  INNER JOIN (SELECT a.vote_id, 
                                                     a.agenda_id, 
                                                     a.score * a.importance as VALUE 
                                              FROM   agendas_agendavote a
                                              JOIN   laws_vote v
                                                ON   a.vote_id = v.id
                                             WHERE   v.time BETWEEN %s and %s) a 
                                    ON p.voteid = a.vote_id) b  
                   GROUP  BY agenda_id, 
                             partyid 
                             ) v 
         ON a.agendaid = v.agenda_id 
            AND a.partyid = v.partyid 
ORDER BY agendaid,score desc"""

def getAllAgendaMkVotes(fromdate=None,todate=None):
    results = None
    isFullQuery = (fromdate is None) and (todate is None)
    if isFullQuery:
        results = cache.get('AllAgendaMemberVotes')
    if not results:
        try:
            if fromdate is None:
                fromdate = 0
            fromdt = datetime.datetime.utcfromtimestamp(float(fromdate))
        except ValueError:
            fromdt = datetime.datetime.utcfromtimestamp(float(0))
        try:
            if todate is None:
                todate = time.time()
            todt = datetime.datetime.utcfromtimestamp(float(todate))
        except ValueError:
            todt = datetime.datetime.utcfromtimestamp(float(time.time()))          
        cursor = connection.cursor()
        cursor.execute(MK_QUERY,[fromdt,todt,fromdt,todt])
        results = dict(map(lambda (key,group):(key,map(lambda g:(g[1],float(g[2]),float(g[3]),int(g[4])),list(group))),
                           groupby(cursor.fetchall(),key=itemgetter(0))))
        if isFullQuery:        
            cache.set('AllAgendaMemberVotes', results, 1800)
    return results

MK_QUERY = """
SELECT a.agendaid, 
       v.memberid, 
       Round(Coalesce(CAST(Coalesce(v.totalvotevalue, 0.0) / a.totalscore * 100.0 AS 
                  NUMERIC),0.0), 2 
       ) score,
       Round(Coalesce(CAST(Coalesce(v.numvotes,0.0) / a.numvotes * 100.0 AS
                  NUMERIC),0.0), 2
       ) volume,
       CAST(Coalesce(v.numvotes,0) AS NUMERIC) numvotes 
FROM   (SELECT a.agenda_id                    agendaid, 
               SUM(Abs(a.score * a.importance)) totalscore,
               COUNT(*) numvotes
        FROM   agendas_agendavote a
        JOIN   laws_vote v
          ON   a.vote_id = v.id
       WHERE   v.time BETWEEN %s and %s
        GROUP  BY a.agenda_id) a 
       LEFT OUTER JOIN (SELECT agenda_id, 
                               memberid, 
                               SUM(forvotes) - SUM(againstvotes) totalvotevalue,
                               SUM(numvotes) numvotes
                        FROM   (SELECT a.agenda_id, 
                                       p.memberid, 
                                       CASE p.vtype 
                                         WHEN 'for' THEN p.numvotes * a.VALUE 
                                         ELSE 0 
                                       END forvotes, 
                                       CASE p.vtype 
                                         WHEN 'against' THEN 
                                         p.numvotes * a.VALUE 
                                         ELSE 0 
                                       END againstvotes, 
                                       p.numvotes numvotes 
                                FROM   (SELECT m.id      memberid, 
                                               v.vote_id voteid, 
                                               v.TYPE    vtype, 
                                               COUNT(*)  numvotes 
                                        FROM   laws_voteaction v 
                                               INNER JOIN mks_member m 
                                                 ON v.member_id = m.id 
                                        WHERE  v.TYPE IN ( 'for', 'against' ) 
                                        GROUP  BY m.id, 
                                                  v.vote_id, 
                                                  v.TYPE) p 
                                       INNER JOIN (SELECT a.vote_id, 
                                                          a.agenda_id, 
                                                          a.score * a.importance AS 
                                                          VALUE 
                                                   FROM   agendas_agendavote a
                                                   JOIN   laws_vote v
                                                     ON   a.vote_id = v.id
                                                  WHERE   v.time BETWEEN %s and %s
                                                   ) a 
                                         ON p.voteid = a.vote_id) b 
                        GROUP  BY agenda_id, 
                                  memberid) v 
         ON a.agendaid = v.agenda_id 
ORDER  BY agendaid, 
          score DESC""" 

def getAgendaEditorIds():
    results = cache.get('AgendaEditorIds')
    if not results:
        cursor = connection.cursor()
        cursor.execute("""SELECT agenda_id,user_id FROM agendas_agenda_editors ORDER BY agenda_id""")
        results = dict(map(lambda (key,group):(key,map(itemgetter(1),list(group))),
                           groupby(cursor.fetchall(),key=itemgetter(0))))
        cache.set('AgendaEditorIds', results, 1800)
    return results
