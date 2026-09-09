"""UI route for provider-independent Room workflow tools."""
from flask import render_template, url_for


def register(bp, app, workflow, csrf):
    app.extensions['room_workflow'] = workflow

    @bp.get('/workflow')
    def workflow_page():
        return render_template(
            'song_builder/workflow.html',
            builder_base_url=url_for('song_builder.index').rstrip('/'),
            builder_assets_url=url_for('song_builder.static', filename=''),
            builder_csrf=csrf(),
        )
