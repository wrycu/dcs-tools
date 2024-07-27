from flask import Blueprint, render_template, current_app, request
from scripts.control_mapper import ControlMapper

mapping = Blueprint('mapping', __name__, url_prefix='/')


@mapping.route('/')
def landing():
    return render_template('mapping/landing.html')


@mapping.route('/upload', methods=['POST'])
def upload():
    """
    TODO
        Throw client-side error if they select >2 files
        Change font size based on character count
        Include axis
            slew button
            slider
        Resize to be kneeboard sized?
        Include none-controller modifiers (e.g. keyboard)
    :return:
    """
    try:
        mapper = ControlMapper()
        stick, throttle = mapper.render_controls(request.files['controls'].read())
        if 'controls2' in request.files:
            # user uploaded two files
            stick2, throttle2 = mapper.render_controls(request.files['controls2'].read())
            # we are not sure which file we parsed first. there are better ways to do this, but this is fastest :0
            if not stick:
                stick = stick2
            elif not throttle:
                throttle = throttle2

        return render_template(
            'mapping/hotas_rendered.html',
            joystick=stick,
            throttle=throttle,
        )
    except Exception as e:
        print(e)
        return str(e), 400
