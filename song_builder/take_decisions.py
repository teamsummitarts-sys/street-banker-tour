"""Account-persistent review decisions for provider candidates."""
import time
from flask import g, jsonify
from . import validation as v


def register(bp, service, body):
    with service.store.connection(write=True) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS room_take_decisions (
          job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          decision TEXT NOT NULL, updated REAL NOT NULL)''')

    @bp.post('/api/projects/<project_id>/jobs/<job_id>/decision')
    def decide_take(project_id, job_id):
        v.identifier(project_id);v.identifier(job_id);p=body('decision')
        if p['decision'] not in ('shortlist','rejected','pending'):v.invalid('Choose shortlist, reject or pending.')
        with service.store.connection(write=True) as db:
            service.store._owned_project(db,g.song_builder_account,project_id)
            row=db.execute('SELECT * FROM jobs WHERE id=? AND owner=? AND project_id=?',(job_id,g.song_builder_account,project_id)).fetchone()
            if row is None:raise v.SongError('not_found','This take is unavailable.',404)
            if row['status']!='succeeded':v.invalid('Wait for this take to finish before reviewing it.')
            db.execute('INSERT INTO room_take_decisions VALUES(?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET decision=excluded.decision,updated=excluded.updated',(job_id,project_id,p['decision'],time.time()))
        return jsonify(decision=p['decision'])
