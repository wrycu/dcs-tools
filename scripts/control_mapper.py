from bs4 import BeautifulSoup as bs
from PIL import Image, ImageDraw, ImageFont
import os
import io
import base64
from pathlib import Path
import glob
SIZE_LARGE = 45
SIZE_NORMAL = 30
SIZE_MEDIUM = 20
SIZE_SMALL = 16
SIZE_STANDARD_NORMAL = 18
SIZE_STANDARD_SMALL = 27
SIZE_VIRPIL_SMALL = 14


class Parser:
    def __init__(self):
        pass

    @staticmethod
    def parse(controls):
        parsed = {
            'controls': {},
            'switches': set(),
        }
        soup = bs(controls, 'html.parser')
        table = bs.find(soup, 'table')

        for row in table.find_all('tr'):
            columns = row.find_all('td')
            if not columns:
                # table header doesn't use data; skip ahead
                continue
            control_a = columns[0].text.replace('"', '').strip()
            # iterate over each bind for the control
            for control in control_a.split('; '):
                # look for a switch
                if control.find(' - ') > 0:
                    parsed['switches'].add(control.split(' - ')[0])
                message = columns[1].text.replace('"', '').strip()
                parsed['controls'][control] = message
        parsed['switches'] = list(parsed['switches'])
        return parsed


class Renderer:
    def __init__(self, controller_type, controller_image):
        self.controller_type = controller_type
        self.controller_image = controller_image
        self.base_path = os.path.join(str(Path(__file__).parent.absolute()), os.pardir)

    def render(self, controls, parent):
        file_path = os.path.join(self.base_path, 'static', 'img')
        # initialise the drawing context with
        # the image object as background
        image = Image.open(os.path.join(file_path, self.controller_image))
        draw = ImageDraw.Draw(image)

        # iterate over bound controls
        for control, name in controls['controls'].items():
            if not control or control in parent.ignore_mapping:
                continue
            if control.find(' - ') > 0:
                switched = True
                control = control.split(' - ')[1]
            else:
                switched = False
            try:
                (x, y, size, hotas) = parent.lookup_position(control, switched)
                if hotas != self.controller_type:
                    # We've pulled a control for an object other than the type we're currently parsing; ignore it
                    continue
            except Exception as e:
                print("unknown control - {} - {}".format(control, e))
                continue
            try:
                the_draw = draw
            except KeyError:
                print("unknown stick type")
                continue
            self.draw_text(the_draw, x, y, size, name)

        for control in controls['switches']:
            if not control or control in parent.ignore_mapping:
                continue
            try:
                (x, y, size, hotas) = parent.lookup_position(control, False)
            except Exception as e:
                print("unknown control - {} - {}".format(control, e))
                continue
            self.draw_text(draw, x, y, size, '(SWITCH)')

        # return the edited images (these are never written to disk)
        output = io.BytesIO()
        io.BytesIO(image.save(output, format='png', compress_level=9))

        output.seek(0)
        return base64.b64encode(output.getvalue()).decode('utf-8')

    def draw_text(self, the_draw, x, y, size, message):
        # add some spaces to reduce the changes of the text being too long
        message = message.replace('/', ' / ')
        message = message.replace('(', ' (')
        message = message.replace('-', ' - ')
        # TODO known bugs:
        # * if a given control has no spaces and is longer than the size permitted, we will hang
        font_size = 18
        if size == SIZE_VIRPIL_SMALL:
            font_size = 14
        font = ImageFont.truetype(
            os.path.join(self.base_path, 'app', 'flask_app', 'static', 'font', 'lucon.ttf'),
            size=font_size,
        )
        color = 'rgb(0, 0, 0)'  # black color
        while len(message) > size:
            position = message[0:size].rfind(' ')
            print(f"now processing {message[0:position]}")
            if position != -1:
                the_draw.text((x, y), message[0:position], fill=color, font=font)
            else:
                position = message[0:size].rfind('/')
                if position != -1:
                    the_draw.text((x, y), message[0:position + 1], fill=color, font=font)
                else:
                    the_draw.text((x, y), message, fill=color, font=font)
                    position = len(message)
            message = message[position + 1:]
            # next line should be 15 pixels down
            y += 15
        # draw the message on the image
        the_draw.text((x, y), message, fill=color, font=font)
        return the_draw


class ControlMapper:
    def __init__(self):
        pass

    def render_controls(self, controls):
        soup = bs(controls, 'html.parser')

        try:
            title = soup.find('h1').next
        except Exception:
            raise Exception("Invalid/malformed file format")

        parser = Parser()
        parsed_controls = parser.parse(controls)

        if len(parsed_controls['switches']) > 1:
            raise Exception("Only one switch key is supported, sorry!")

        if parsed_controls['switches']:
            switch_key = parsed_controls['switches'][0]
        else:
            switch_key = None

        # detect controller and validate we support it
        print(title)
        if 'X52' in title:
            controller = X52(switch_key)
        elif 'Warthog' in title:
            if 'Joystick' in title:
                controller = WarthogStick(switch_key)
            elif 'Throttle' in title:
                controller = WarthogThrottle(switch_key)
        elif 'X56' in title:
            if 'Stick' in title:
                controller = X56Stick(switch_key)
            elif 'Throttle' in title:
                controller = X56Throttle(switch_key)
        elif 'VPC Stick' in title:
            controller = MongoosT50CM2(switch_key)
        elif 'VPC Throttle' in title:
            controller = MT50CM3(switch_key)
        else:
            raise Exception(
                "Unknown controller: {}. Supported controllers: X-52, X-56, Warthog".format(title)
            )

        if controller.render_stick:
            stick_image = Renderer('stick', controller.stick_file).render(parsed_controls, controller)
        else:
            stick_image = None
        if controller.render_throttle:
            throttle_image = Renderer('throttle', controller.throttle_file).render(parsed_controls, controller)
        else:
            throttle_image = None

        return stick_image, throttle_image


class X52:
    def __init__(self, switch_key=None):
        """
        Mapping of buttons to actual buttons

        Stick
            Fire                JOY_BTN2        530, 135        530, 205
            Fire A              JOY_BTN3        1350, 114       1350, 183
            Fire B              JOY_BTN4        1350, 295       1350, 364
            Fire C              JOY_BTN5        530, 363        530, 433
            POV Hat 1           --------
                Up              JOY_BTN_POV1_U  75, 355         333, 355
                Down            JOY_BTN_POV1_D  75, 495         333, 495
                Left            JOY_BTN_POV1_L  5, 423          263, 423
                Right           JOY_BTN_POV1_R  140, 423        396, 423
            POV Hat 2           ---------
                Up              JOY_BTN16       75, 122         333, 122
                Down            JOY_BTN18       75, 262         333, 262
                Left            JOY_BTN19       5, 190          263, 190
                Right           JOY_BTN17       140, 190        396, 190
            Trigger             JOY_BTN1        1350, 474       1350, 542
            Second Trigger      JOY_BTN15       1620, 474       1620, 542
            Toggle 1            JOY_BTN9        103, 622        103, 774
            Toggle 2            JOY_BTN10       103, 692        103, 844
            Toggle 3            JOY_BTN11       230, 622        230, 774
            Toggle 4            JOY_BTN12       230, 692        230, 844
            Toggle 5            JOY_BTN13       358, 622        358, 774
            Toggle 6            JOY_BTN14       358, 692        358, 844
            Pinkie Switch       JOY_BTN6
            Mode 1              JOY_BTN24       1620, 107
            Mode 2              JOY_BTN25       1620. 174
            Mode 3              JOY_BTN26       1620, 244
        Throttle
            Fire D              JOY_BTN7        1365, 1180      1597, 1180
            Fire E              JOY_BTN8        1365, 968       1597, 968
            Rotary 1
                Clockwise
                C-Clockwise
            Rotary 2
                Clockwise
                C-Clockwise
            POV Hat 3
                Up              JOY_BTN20       78, 940         332, 940
                Down            JOY_BTN22       78, 1081        332, 1081
                Left            JOY_BTN23       7, 1011         267, 1011
                Right           JOY_BTN21       142, 1013       400, 1013
            Ministick
            Throttle Base 1     JOY_BTN27       5, 1500         5, 1582
            Throttle Base 2     JOY_BTN28       130, 1500       130, 1582
            Throttle Base 3     JOY_BTN29       258, 1500       2556, 1582
            Precision Slider
            Clutch Fixed
        """
        self.name = 'x52'
        self.controller_type = 'hotas'
        self.ignore_mapping = {
            'JOY_Z',
            'JOY_Y',
            'JOY_X',
            'JOY_RZ',
            'JOY_RY',
            'JOY_RX',
        }
        self.switches = []
        self.stick_file = 'x52_stick.png'
        self.throttle_file = 'x52_throttle.png'
        self.render_stick = True
        self.render_throttle = True

        self.switch_key = ''  # 'JOY_BTN6 - '

        self.control_mapping = {
            # Joystick
            'JOY_BTN2': 'fire',
            self.switch_key + 'JOY_BTN2': 'fire_s',
            'JOY_BTN3': 'fire_a',
            self.switch_key + 'JOY_BTN3': 'fire_a_s',
            'JOY_BTN4': 'fire_b',
            self.switch_key + 'JOY_BTN4': 'fire_b_s',
            'JOY_BTN5': 'fire_c',
            self.switch_key + 'JOY_BTN5': 'fire_c_s',
            'JOY_BTN_POV1_U': 'pov_1_up',
            'JOY_BTN_POV1_D': 'pov_1_down',
            'JOY_BTN_POV1_L': 'pov_1_left',
            'JOY_BTN_POV1_R': 'pov_1_right',
            self.switch_key + 'JOY_BTN_POV1_U': 'pov_1_s_up',
            self.switch_key + 'JOY_BTN_POV1_D': 'pov_1_s_down',
            self.switch_key + 'JOY_BTN_POV1_L': 'pov_1_s_left',
            self.switch_key + 'JOY_BTN_POV1_R': 'pov_1_s_right',
            'JOY_BTN16': 'pov_2_up',
            'JOY_BTN18': 'pov_2_down',
            'JOY_BTN19': 'pov_2_left',
            'JOY_BTN17': 'pov_2_right',
            self.switch_key + 'JOY_BTN16': 'pov_2_s_up',
            self.switch_key + 'JOY_BTN18': 'pov_2_s_down',
            self.switch_key + 'JOY_BTN19': 'pov_2_s_left',
            self.switch_key + 'JOY_BTN17': 'pov_2_s_right',
            'JOY_BTN1': 'trigger',
            self.switch_key + 'JOY_BTN1': 'trigger_s',
            'JOY_BTN15': 'trigger_2',
            self.switch_key + 'JOY_BTN15': 'trigger_2_s',
            'JOY_BTN9': 't_1',
            'JOY_BTN10': 't_2',
            'JOY_BTN11': 't_3',
            'JOY_BTN12': 't_4',
            'JOY_BTN13': 't_5',
            'JOY_BTN14': 't_6',
            self.switch_key + 'JOY_BTN9': 't_1_s',
            self.switch_key + 'JOY_BTN10': 't_2_s',
            self.switch_key + 'JOY_BTN11': 't_3_s',
            self.switch_key + 'JOY_BTN12': 't_4_s',
            self.switch_key + 'JOY_BTN13': 't_5_s',
            self.switch_key + 'JOY_BTN14': 't_6_s',
            'JOY_BTN6': 'Pinkie Switch',
            # Throttle
            'JOY_BTN7': 'fire_d',
            self.switch_key + 'JOY_BTN7': 'fire_d_s',
            'JOY_BTN8': 'fire_e',
            self.switch_key + 'JOY_BTN8': 'fire_e_s',
            'JOY_BTN20': 'pov_3_up',
            'JOY_BTN22': 'pov_3_down',
            'JOY_BTN23': 'pov_3_left',
            'JOY_BTN21': 'pov_3_right',
            self.switch_key + 'JOY_BTN20': 'pov_3_s_up',
            self.switch_key + 'JOY_BTN22': 'pov_3_s_down',
            self.switch_key + 'JOY_BTN23': 'pov_3_s_left',
            self.switch_key + 'JOY_BTN21': 'pov_3_s_right',
            'JOY_BTN27': 'throttle_1',
            'JOY_BTN28': 'throttle_2',
            'JOY_BTN29': 'throttle_3',
            self.switch_key + 'JOY_BTN27': 'throttle_1_s',
            self.switch_key + 'JOY_BTN28': 'throttle_2_s',
            self.switch_key + 'JOY_BTN29': 'throttle_3_s',
            'JOY_BTN24': 'm_1',
            'JOY_BTN25': 'm_2',
            'JOY_BTN26': 'm_3',
            'JOY_BTN31': 'm_b_1',
            self.switch_key + 'JOY_BTN31': 'm_b_s_1',
            'JOY_BTN33': 'm_w_2_d',
            'JOY_BTN34': 'm_w_2_u',
        }

        self.position_mapping = {
            # Joystick
            'JOY_BTN2': (672, 5, SIZE_STANDARD_NORMAL, 'stick'),                              # fire
            'JOY_BTN3': (902, 5, SIZE_STANDARD_NORMAL, 'stick'),                             # fire A
            'JOY_BTN4': (902, 325, SIZE_STANDARD_NORMAL, 'stick'),                             # fire B
            'JOY_BTN5': (482, 412, SIZE_STANDARD_NORMAL, 'stick'),                              # fire C
            'JOY_BTN_POV1_U': (122, 505, SIZE_STANDARD_NORMAL, 'stick'),                         # pov hat 1 up
            'JOY_BTN_POV1_D': (122, 645, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN_POV1_L': (22, 575, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN_POV1_R': (242, 575, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN16': (122, 35, SIZE_STANDARD_NORMAL, 'stick'),                              # pov hat 2 up
            'JOY_BTN18': (122, 175, SIZE_STANDARD_NORMAL, 'stick'),                              # down
            'JOY_BTN19': (22, 105, SIZE_STANDARD_NORMAL, 'stick'),                               # left -13
            'JOY_BTN17': (242, 105, SIZE_STANDARD_NORMAL, 'stick'),                             # right
            'JOY_BTN1': (1212, 395, SIZE_STANDARD_NORMAL, 'stick'),                             # trigger
            'JOY_BTN15': (1212, 575, SIZE_STANDARD_NORMAL, 'stick'),                            # stage 2 trigger
            'JOY_BTN9': (502, 865, SIZE_STANDARD_NORMAL, 'stick'),                              # t1
            'JOY_BTN10': (502, 935, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN11': (722, 865, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN12': (722, 935, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN13': (942, 865, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN14': (942, 935, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN6': (1212, 760, SIZE_STANDARD_NORMAL, 'stick'),                                   # pinkie switch
            'JOY_BTN24': (1212, 105, SIZE_STANDARD_NORMAL, 'stick'),                             # mode 1
            'JOY_BTN25': (1212, 175, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN26': (1212, 245, SIZE_STANDARD_NORMAL, 'stick'),
            # Throttle
            'JOY_BTN7': (752, 455, SIZE_STANDARD_NORMAL, 'throttle'),                            # fire D
            'JOY_BTN8': (522, 305, SIZE_STANDARD_NORMAL, 'throttle'),                             # fire E
            'JOY_BTN20': (157, 35, SIZE_STANDARD_NORMAL, 'throttle'),                              # pov 3 up
            'JOY_BTN22': (157, 175, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN23': (57, 105, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN21': (277, 105, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN27': (2, 1015, SIZE_STANDARD_NORMAL, 'throttle'),                              # throttle 1
            'JOY_BTN28': (222, 1015, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN29': (442, 1015, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN31': (2, 635, SIZE_STANDARD_NORMAL, 'throttle'),                            # mouse button 1
        }

        self.switched_mapping = {
            # Joystick
            'JOY_BTN2': (672, 75, SIZE_STANDARD_NORMAL, 'stick'),  # fire switched
            'JOY_BTN3': (902, 75, SIZE_STANDARD_NORMAL, 'stick'),  # fire A switched
            'JOY_BTN4': (902, 395, SIZE_STANDARD_NORMAL, 'stick'),  # fire B switched
            'JOY_BTN5': (482, 480, SIZE_STANDARD_NORMAL, 'stick'),  # fire C switched
            'JOY_BTN_POV1_U': (122, 725, SIZE_STANDARD_NORMAL, 'stick'),    # fire pov hat 1
            'JOY_BTN_POV1_D': (122, 865, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN_POV1_L': (22, 795, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN_POV1_R': (242, 795, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN16': (122, 255, SIZE_STANDARD_NORMAL, 'stick'),  # pov hat 2 up switched
            'JOY_BTN18': (122, 395, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN19': (22, 325, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN17': (242, 325, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN1': (1212, 465, SIZE_STANDARD_NORMAL, 'stick'),  # trigger switched
            'JOY_BTN15': (1212, 645, SIZE_STANDARD_NORMAL, 'stick'),  # stage 2 trigger switched
            'JOY_BTN9': (502, 1005, SIZE_STANDARD_NORMAL, 'stick'),  # t1 switched
            'JOY_BTN10': (502, 1075, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN11': (722, 1005, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN12': (722, 1075, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN13': (942, 1005, SIZE_STANDARD_NORMAL, 'stick'),
            'JOY_BTN14': (942, 1075, SIZE_STANDARD_NORMAL, 'stick'),
            # Throttle
            'JOY_BTN7': (757, 525, SIZE_STANDARD_NORMAL, 'throttle'),  # fire D switched
            'JOY_BTN8': (522, 375, SIZE_STANDARD_NORMAL, 'throttle'),   # fire E switched
            'JOY_BTN20': (157, 255, SIZE_STANDARD_NORMAL, 'throttle'),  # pov 3 up switched
            'JOY_BTN22': (157, 395, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN23': (57, 325, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN21': (277, 325, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN27': (2, 1085, SIZE_STANDARD_NORMAL, 'throttle'),    # throttle 1
            'JOY_BTN28': (222, 1085, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN29': (442, 1085, SIZE_STANDARD_NORMAL, 'throttle'),
            'JOY_BTN31': (2, 705, SIZE_STANDARD_NORMAL, 'throttle'),  # mb 1 switched
        }

    def add_switch(self, control):
        if control not in self.control_mapping:
            raise Exception("Unknown switch detected - {}".format(control))
        self.switches.append(control)

    def lookup_control(self, control):
        if not control:
            return None, None
        try:
            return self.control_mapping[control], False
        except KeyError:
            try:
                return self.control_mapping[control], True
            except KeyError:
                return None, None

    def lookup_position(self, control, switched):
        if switched:
            return self.switched_mapping[control]
        else:
            return self.position_mapping[control]


class WarthogStick:
    def __init__(self, switch_key):
        """
                Mapping of buttons to actual buttons

                Stick
                    Fire                JOY_BTN2
                    TMS FWD             JOY_BTN7
                    TMS AFT             JOY_BTN9
                    TMS LEFT            JOY_BTN10
                    TMS RIGHT           JOY_BTN8
                    DMS FWD             JOY_BTN11
                    DMS AFT             JOY_BTN13
                    DMS LEFT            JOY_BTN14
                    DMS RIGHT           JOY_BTN12
                    TRIM DOWN           JOY_BTN_POV1_D
                    TRIM UP             JOY_BTN_POV1_U
                    TRIM LEFT           JOY_BTN_POV1_L
                    TRIM RIGHT          JOY_BTN_POV1_R
                    CMS FWD             JOY_BTN15
                    CMS AFT             JOY_BTN17
                    CMS LEFT            JOY_BTN18
                    CMS RIGHT           JOY_BTN16
                    CMS DOWN            JOY_BTN19
                    MASTER MODE         JOY_BTN5
                    WEAPON RELEASE      JOY_BTN2
                    TRIGGER             JOY_BTN1
                    TRIGGER 2           JOY_BTN6
                    NSB                 JOY_BTN3
                    PINKIE              JOY_BTN4

        """
        self.name = 'warthog_stick'
        self.controller_type = 'hotas'
        self.ignore_mapping = {
            'JOY_Z',
            'JOY_Y',
            'JOY_X',
            'JOY_RZ',
            'JOY_RY',
            'JOY_RX',
        }
        self.switches = []
        self.stick_file = 'warthog_stick.png'
        self.render_stick = True
        self.render_throttle = False

        self.switch_key = switch_key

        self.control_mapping = {}
        self.position_mapping = {}
        self.switched_mapping = {}

        # to determine these numbers, add two to the left value and five to the top value
        self.add_control('tms_fwd', 'JOY_BTN7', 122, 35, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('tms_aft', 'JOY_BTN9', 122, 175, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('tms_left', 'JOY_BTN10', 22, 105, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('tms_right', 'JOY_BTN8', 242, 105, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('weapon_release', 'JOY_BTN2', 482, 105, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('trim_up', 'JOY_BTN_POV1_U', 812, 35, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('trim_down', 'JOY_BTN_POV1_D', 812, 175, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('trim_left', 'JOY_BTN_POV1_L', 712, 105, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('trim_right', 'JOY_BTN_POV1_R', 932, 105, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('master_mode', 'JOY_BTN5', 1122, 735, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('dms_fwd', 'JOY_BTN11', 812, 955, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('dms_aft', 'JOY_BTN13', 812, 1095, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('dms_left', 'JOY_BTN14', 712, 1025, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('dms_right', 'JOY_BTN12', 932, 1025, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('cms_fwd', 'JOY_BTN15', 232, 925, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('cms_aft', 'JOY_BTN17', 232, 1065, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('cms_left', 'JOY_BTN18', 132, 995, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('cms_right', 'JOY_BTN16', 352, 995, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('cms_down', 'JOY_BTN19', 12, 1065, SIZE_STANDARD_NORMAL, 'stick')  # missing
        self.add_control('nose_wheel_steering', 'JOY_BTN3', 162, 795, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('r_pinkie_switch', 'JOY_BTN4', 162, 695, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('weapon_fire_2', 'JOY_BTN6', 162, 595, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('weapon_fire', 'JOY_BTN1', 162, 505, SIZE_STANDARD_NORMAL, 'stick')

        # Switched
        if switch_key:
            self.add_control('tms_fwd_s', 'JOY_BTN7', 122, 255, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('tms_aft_s', 'JOY_BTN9', 122, 395, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('tms_left_s', 'JOY_BTN10', 22, 325, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('tms_right_s', 'JOY_BTN8', 242, 325, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('weapon_release_s', 'JOY_BTN2', 482, 185, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('trim_up_s', 'JOY_BTN_POV1_U', 1272, 35, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('trim_down_s', 'JOY_BTN_POV1_D', 1272, 175, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('trim_left_s', 'JOY_BTN_POV1_L', 1172, 105, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('trim_right_s', 'JOY_BTN_POV1_R', 1392, 105, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('master_mode_s', 'JOY_BTN5', 1342, 735, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('dms_fwd_s', 'JOY_BTN11', 1272, 955, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('dms_aft_s', 'JOY_BTN13', 1272, 1095, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('dms_left_s', 'JOY_BTN14', 1172, 1025, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('dms_right_s', 'JOY_BTN12', 1392, 1025, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('cms_fwd_s', 'JOY_BTN15', 232, 1145, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('cms_aft_s', 'JOY_BTN17', 232, 1285, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('cms_left_s', 'JOY_BTN18', 132, 1210, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('cms_right_s', 'JOY_BTN16', 352, 1210, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('cms_down_s', 'JOY_BTN19', 12, 1285, SIZE_STANDARD_NORMAL, 'stick')  # missing
            self.add_control('nose_wheel_steering_s', 'JOY_BTN3', 382, 795, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('r_pinkie_switch_s', 'JOY_BTN4', 382, 695, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('weapon_fire_2_s', 'JOY_BTN6', 382, 595, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('weapon_fire_s', 'JOY_BTN1', 382, 505, SIZE_STANDARD_NORMAL, 'stick')

    def add_control(self, friendly_name, technical_name, x, y, size, location):
        """
        :param friendly_name:
            e.g. 'Boat Switch FWD'
        :param technical_name:
            e.g. 'JOY_BTN9'
        :param x:
            e.g. 42
        :param y:
            e.g. 899
        :param size:
            e.g. SIZE_STANDARD_NORMAL
        :param location:
            e.g. 'throttle'
        :return:
            N/A
        """
        if friendly_name[-2:] != '_s':
            self.control_mapping[technical_name] = friendly_name
            self.position_mapping[technical_name] = (x, y, size, location)
        else:
            self.control_mapping[self.switch_key + technical_name] = friendly_name
            self.switched_mapping[technical_name] = (x, y, size, location)

    def add_switch(self, control):
        if control not in self.control_mapping:
            raise Exception("Unknown switch detected - {}".format(control))
        self.switches.append(control)

    def lookup_control(self, control):
        if not control:
            return None, None
        try:
            return self.control_mapping[control], False
        except KeyError:
            try:
                return self.control_mapping[control], True
            except KeyError:
                return None, None

    def lookup_position(self, control, switched):
        if control not in self.position_mapping.keys() and not switched:
            # this control doesn't actually exist
            raise Exception("Control does not exist")
        if switched:
            return self.switched_mapping[control]
        else:
            return self.position_mapping[control]


class WarthogThrottle:
    def __init__(self, switch_key):
        """
                Mapping of buttons to actual buttons
                Coolie Switch Up    JOY_BTN_POV1_U
                Coolie Switch Down  JOY_BTN_POV1_D
                Coolie Switch Left  JOY_BTN_POV1_L
                Coolie Switch Right JOY_BTN_POV1_R
                Mic Switch FWD      JOY_BTN4
                Mic Switch AFT      JOY_BTN6
                Mic Switch LEFT     JOY_BTN3
                Mic Switch RIGHT    JOY_BTN5
                SPEEDBRAKE OUT      JOY_BTN7
                SPEEDBRAKE IN       JOY_BTN8
                Boat switch FWD     JOY_BTN9
                Boat Switch AFT     JOY_BTN10
                China Hat FWD       JOY_BTN11
                China Hat AFT       JOY_BTN12
                Throttle Button     JOY_BTN15
                Pinkie Switch FWD   JOY_BTN13
                Pinkie Swift AFT    JOY_BTN14
                FLAPS UP            JOY_BTN22
                FLAPS DWN           JOY_BTN23

                EAC                 JOY_BTN24
                RDR ALTM            JOY_BTN25
                AP                  JOY_BTN26
                LASTE / PATH        JOY_BTN27
                LASTE / ALT         JOY_BTN28
                L/G WRN             JOY_BTN21
                flaps up            JOY_BTN22
                flaps down          JOY_BTN23
                APU start           JOY_BTN20
                IGN L               JOY_BTN18 | JOY_BTN31
                IGN R               JOY_BTN19 | JOY_BTN32
                ENG FLOW L          JOY_BTN16
                ENG FLOW R          JOY_BTN17
                Note - slew press is not covered currently
        """
        self.name = 'warthog_throttle'
        self.controller_type = 'hotas'
        self.ignore_mapping = {
            'JOY_Z',
            'JOY_Y',
            'JOY_X',
            'JOY_RZ',
            'JOY_RY',
            'JOY_RX',
        }
        self.switches = []
        self.throttle_file = 'warthog_throttle.png'
        self.render_stick = False
        self.render_throttle = True

        self.switch_key = switch_key
        self.control_mapping = {}
        self.position_mapping = {}
        self.switched_mapping = {}

        self.add_control('mic_switch_fwd', 'JOY_BTN4', 112, 15, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('mic_switch_aft', 'JOY_BTN6', 112, 155, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('mic_switch_left', 'JOY_BTN3', 12, 85, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('mic_switch_right', 'JOY_BTN5', 232, 85, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('coolie_switch_up', 'JOY_BTN_POV1_U', 1032, 15, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('coolie_switch_down', 'JOY_BTN_POV1_D', 1032, 155, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('coolie_switch_left', 'JOY_BTN_POV1_L', 932, 85, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('coolie_switch_right', 'JOY_BTN_POV1_R', 1152, 85, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('throttle_button', 'JOY_BTN15', 1412, 285, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('l_pinkie_switch_fwd', 'JOY_BTN13', 1412, 405, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('l_pinkie_switch_aft', 'JOY_BTN14', 1632, 385, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('ign_l', 'JOY_BTN18', 1412, 655, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('ign_r', 'JOY_BTN19', 1632, 655, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('eng_l', 'JOY_BTN16', 1412, 730, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('eng_r', 'JOY_BTN17', 1632, 730, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('apu', 'JOY_BTN20', 1412, 865, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('lg_warn', 'JOY_BTN21', 922, 825, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('laste_path', 'JOY_BTN27', 922, 925, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('laste_alt', 'JOY_BTN28', 922, 1025, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('eac', 'JOY_BTN24', 472, 825, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('rdr_alt', 'JOY_BTN25', 472, 925, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('ap', 'JOY_BTN26', 472, 1025, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('flaps_up', 'JOY_BTN22', 12, 955, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('flaps_down', 'JOY_BTN23', 232, 955, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('china_hat_fwd', 'JOY_BTN11', 12, 735, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('china_hat_aft', 'JOY_BTN12', 232, 735, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('boat_switch_fwd', 'JOY_BTN9', 12, 520, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('boat_switch_aft', 'JOY_BTN10', 232, 520, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('speedbrake_in', 'JOY_BTN8', 12, 235, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('speedbrake_out', 'JOY_BTN7', 232, 235, SIZE_STANDARD_NORMAL, 'throttle')

        # Switched
        if switch_key:
            self.add_control('mic_switch_fwd_s', 'JOY_BTN4', 572, 15, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('mic_switch_aft_s', 'JOY_BTN6', 572, 155, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('mic_switch_left_s', 'JOY_BTN3', 472, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('mic_switch_right_s', 'JOY_BTN5', 692, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('coolie_switch_up_s', 'JOY_BTN_POV1_U', 1492, 15, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('coolie_switch_down_s', 'JOY_BTN_POV1_D', 1492, 155, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('coolie_switch_left_s', 'JOY_BTN_POV1_L', 1392, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('coolie_switch_right_s', 'JOY_BTN_POV1_R', 1612, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('throttle_button_s', 'JOY_BTN15', 1632, 285, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('l_pinkie_switch_fwd_s', 'JOY_BTN13', 1412, 455, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('l_pinkie_switch_aft_s', 'JOY_BTN14', 1632, 455, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('apu_s', 'JOY_BTN20', 1632, 865, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('lg_warn_s', 'JOY_BTN21', 1142, 825, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('laste_path_s', 'JOY_BTN27', 1142, 925, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('laste_alt_s', 'JOY_BTN28', 1142, 1025, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('eac_s', 'JOY_BTN24', 692, 825, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('rdr_alt_s', 'JOY_BTN25', 692, 925, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('ap_s', 'JOY_BTN26', 692, 1025, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('flaps_up_s', 'JOY_BTN22', 12, 1025, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('flaps_down_s', 'JOY_BTN23', 232, 1025, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('china_hat_fwd_s', 'JOY_BTN11', 12, 805, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('china_hat_aft_s', 'JOY_BTN12', 232, 805, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('boat_switch_fwd_s', 'JOY_BTN9', 12, 590, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('boat_switch_aft_s', 'JOY_BTN10', 232, 590, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('speedbrake_in_s', 'JOY_BTN8', 12, 305, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('speedbrake_out_s', 'JOY_BTN7', 232, 305, SIZE_STANDARD_NORMAL, 'throttle')

    def add_control(self, friendly_name, technical_name, x, y, size, location):
        """
        :param friendly_name:
            e.g. 'Boat Switch FWD'
        :param technical_name:
            e.g. 'JOY_BTN9'
        :param x:
            e.g. 42
        :param y:
            e.g. 899
        :param size:
            e.g. SIZE_STANDARD_NORMAL
        :param location:
            e.g. 'throttle'
        :return:
            N/A
        """
        if friendly_name[-2:] != '_s':
            self.control_mapping[technical_name] = friendly_name
            self.position_mapping[technical_name] = (x, y, size, location)
        else:
            self.control_mapping[self.switch_key + technical_name] = friendly_name
            self.switched_mapping[technical_name] = (x, y, size, location)

    def add_switch(self, control):
        if control not in self.control_mapping:
            raise Exception("Unknown switch detected - {}".format(control))
        self.switches.append(control)

    def lookup_control(self, control):
        if not control:
            return None, None
        try:
            return self.control_mapping[control], False
        except KeyError:
            try:
                return self.control_mapping[control], True
            except KeyError:
                return None, None

    def lookup_position(self, control, switched):
        if control not in self.position_mapping.keys() and not switched:
            # this control doesn't actually exist
            raise Exception("Control does not exist")
        if switched:
            return self.switched_mapping[control]
        else:
            return self.position_mapping[control]


class X56Stick:
    def __init__(self, switch_key):
        """
                Mapping of buttons to actual buttons
                Index               JOY_BTN1
                Pinky_D             JOY_BTN5
                Pinky_TRG           JOY_BTN6
                C Stick Press       JOY_BTN4
                Hat 1 Up            JOY_BTN7
                Hat 1 Down          JOY_BTN9
                Hat 1 Left          JOY_BTN10
                Hat 1 Right         JOY_BTN8
                Stick Right Button  JOY_BTN3
                Hat 2 Up            JOY_BTN11
                Hat 2 Down          JOY_BTN13
                Hat 2 Left          JOY_BTN14
                Hat 2 Right         JOY_BTN12
                POV 1 Up            JOY_BTN_POV1_U
                POV 1 Down          JOY_BTN_POV1_D
                POV 1 Left          JOY_BTN_POV1_L
                POV 1 Right         JOY_BTN_POV1_R
                Stick Top Button    JOY_BTN2
        """
        self.name = 'x56_stick'
        self.controller_type = 'hotas'
        self.ignore_mapping = {
            'JOY_Z',
            'JOY_Y',
            'JOY_X',
            'JOY_RZ',
            'JOY_RY',
            'JOY_RX',
        }
        self.switches = []
        self.stick_file = 'x56_stick.png'
        self.render_stick = True
        self.render_throttle = False

        self.switch_key = switch_key
        self.control_mapping = {}
        self.position_mapping = {}
        self.switched_mapping = {}

        self.add_control('index', 'JOY_BTN1', 122, 515, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('pinky_d', 'JOY_BTN5', 822, 805, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('pinky_trg', 'JOY_BTN6', 822, 599, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('c_stick_press', 'JOY_BTN4', 122, 696, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_1_up', 'JOY_BTN7', 822, 45, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_1_down', 'JOY_BTN9', 822, 185, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_1_left', 'JOY_BTN10', 722, 115, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_1_right', 'JOY_BTN8', 942, 115, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('stick_right_button', 'JOY_BTN3', 1072, 599, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_2_up', 'JOY_BTN11', 822, 335, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_2_down', 'JOY_BTN13', 822, 475, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_2_left', 'JOY_BTN14', 722, 405, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('hat_2_right', 'JOY_BTN12', 942, 405, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('pov_1_up', 'JOY_BTN_POV1_U', 122, 25, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('pov_1_down', 'JOY_BTN_POV1_D', 122, 165, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('pov_1_left', 'JOY_BTN_POV1_L', 22, 95, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('pov_1_right', 'JOY_BTN_POV1_R', 242, 95, SIZE_STANDARD_NORMAL, 'stick')
        self.add_control('stick_top_button', 'JOY_BTN2', 482, 95, SIZE_STANDARD_NORMAL, 'stick')

        # Switched
        if switch_key:
            self.add_control('index_s', 'JOY_BTN1', 122, 585, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('pinky_d_s', 'JOY_BTN5', 822, 875, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('pinky_trg_s', 'JOY_BTN6', 820, 669, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('c_stick_press_s', 'JOY_BTN4', 122, 766, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_1_up_s', 'JOY_BTN7', 1282, 45, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_1_down_s', 'JOY_BTN9', 1282, 185, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_1_left_s', 'JOY_BTN10', 1182, 115, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_1_right_s', 'JOY_BTN8', 1402, 115, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('stick_right_button_s', 'JOY_BTN3', 1072, 669, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_2_up_s', 'JOY_BTN11', 1282, 335, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_2_down_s', 'JOY_BTN13', 1282, 475, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_2_left_s', 'JOY_BTN14', 1182, 405, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('hat_2_right_s', 'JOY_BTN12', 1402, 405, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('pov_1_up_s', 'JOY_BTN_POV1_U', 122, 235, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('pov_1_down_s', 'JOY_BTN_POV1_D', 122, 375, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('pov_1_left_s', 'JOY_BTN_POV1_L', 22, 305, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('pov_1_right_s', 'JOY_BTN_POV1_R', 242, 305, SIZE_STANDARD_NORMAL, 'stick')
            self.add_control('stick_top_button_s', 'JOY_BTN2', 482, 165, SIZE_STANDARD_NORMAL, 'stick')

    def add_control(self, friendly_name, technical_name, x, y, size, location):
        """
        :param friendly_name:
            e.g. 'Boat Switch FWD'
        :param technical_name:
            e.g. 'JOY_BTN9'
        :param x:
            e.g. 42
        :param y:
            e.g. 899
        :param size:
            e.g. SIZE_STANDARD_NORMAL
        :param location:
            e.g. 'throttle'
        :return:
            N/A
        """
        if friendly_name[-2:] != '_s':
            self.control_mapping[technical_name] = friendly_name
            self.position_mapping[technical_name] = (x, y, size, location)
        else:
            self.control_mapping[self.switch_key + technical_name] = friendly_name
            self.switched_mapping[technical_name] = (x, y, size, location)

    def add_switch(self, control):
        if control not in self.control_mapping:
            raise Exception("Unknown switch detected - {}".format(control))
        self.switches.append(control)

    def lookup_control(self, control):
        if not control:
            return None, None
        try:
            return self.control_mapping[control], False
        except KeyError:
            try:
                return self.control_mapping[control], True
            except KeyError:
                return None, None

    def lookup_position(self, control, switched):
        if control not in self.position_mapping.keys() and not switched:
            # this control doesn't actually exist
            raise Exception("Control does not exist")
        if switched:
            return self.switched_mapping[control]
        else:
            return self.position_mapping[control]


class X56Throttle:
    def __init__(self, switch_key):
        """
                Mapping of buttons to actual buttons
                K1_UP               JOY_BTN28
                K1_DOWN             JOY_BTN29
                throttle_b_4        JOY_BTN4
                throttle_b_5        JOY_BTN5
                tgl_4_up            JOY_BTN18
                tgl_4_down          JOY_BTN19
                tgl_3_up            JOY_BTN16
                tgl_3_down          JOY_BTN17
                tgl_2_up            JOY_BTN14
                tgl_2_down          JOY_BTN15
                tgl_1_up            JOY_BTN12
                tgl_1_down          JOY_BTN13
                rty_1               JOY_Z
                rty_2               JOY_RZ
                rty_3               JOY_SLIDER1
                rty_4               JOY_SLIDER2
                hat_3_up            JOY_BTN21
                hat_3_down          JOY_BTN23
                hat_3_left          JOY_BTN20
                hat_3_right         JOY_BTN22
                hat_4_up            JOY_BTN25
                hat_4_down          JOY_BTN27
                hat_4_left          JOY_BTN24
                hat_4_right         JOY_BTN26
                switch_1            JOY_BTN6
                switch_2            JOY_BTN7
                switch_3            JOY_BTN8
                switch_4            JOY_BTN9
                switch_5            JOY_BTN10
                switch_6            JOY_BTN11
                mode_1              ?
                mode_2              ?
                mode_3              ?
                scroll_plus         JOY_BTN30
                scroll_minus        JOY_BTN31
                thumb_1             JOY_BTN33
                thumb_2             JOY_BTN1
        """
        self.name = 'x56_throttle'
        self.controller_type = 'hotas'
        self.ignore_mapping = {
            'JOY_Y',
            'JOY_X',
            'JOY_RY',
            'JOY_RX',
        }
        self.switches = []
        self.throttle_file = 'x56_throttle.png'
        self.render_stick = False
        self.render_throttle = True

        self.switch_key = switch_key
        self.control_mapping = {}
        self.position_mapping = {}
        self.switched_mapping = {}

        self.add_control('k1_up', 'JOY_BTN28', 292, 15, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('k1_down', 'JOY_BTN29', 502, 15, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('throttle_b_4', 'JOY_BTN4', 517, 205, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('throttle_b_5', 'JOY_BTN5', 732, 15, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_4_up', 'JOY_BTN18', 1217, 865, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_4_down', 'JOY_BTN19', 1217, 1005, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_3_up', 'JOY_BTN16', 997, 865, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_3_down', 'JOY_BTN17', 997, 1005, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_2_up', 'JOY_BTN14', 777, 865, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_2_down', 'JOY_BTN15', 777, 1005, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_1_up', 'JOY_BTN12', 557, 865, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('toggle_1_down', 'JOY_BTN13', 557, 1005, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('rty_1', 'JOY_Z', 742, 285, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('rty_2', 'JOY_RZ', 1197, 265, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('rty_3', 'JOY_SLIDER1', 317, 1005, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('rty_4', 'JOY_SLIDER2', 97, 1005, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_3_up', 'JOY_BTN21', 1107, 405, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_3_down', 'JOY_BTN23', 1107, 545, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_3_left', 'JOY_BTN20', 1007, 475, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_3_right', 'JOY_BTN22', 1227, 475, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_4_up', 'JOY_BTN25', 1537, 715, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_4_down', 'JOY_BTN27', 1537, 855, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_4_left', 'JOY_BTN24', 1437, 785, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('hat_4_right', 'JOY_BTN26', 1657, 785, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('switch_1', 'JOY_BTN6', 257, 415, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('switch_2', 'JOY_BTN7', 257, 577, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('switch_3', 'JOY_BTN8', 17, 285, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('switch_4', 'JOY_BTN9', 17, 465, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('switch_5', 'JOY_BTN10', 17, 625, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('switch_6', 'JOY_BTN11', 17, 795, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('scroll_plus', 'JOY_BTN30', 292, 205, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('scroll_minus', 'JOY_BTN31', 292, 275, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('thumb_button_1', 'JOY_BTN33', 957, 15, SIZE_STANDARD_NORMAL, 'throttle')
        self.add_control('thumb_button_2', 'JOY_BTN1', 977, 195, SIZE_STANDARD_NORMAL, 'throttle')

        # Switched
        if switch_key:
            self.add_control('k1_up_s', 'JOY_BTN28', 292, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('k1_down_s', 'JOY_BTN29', 502, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('throttle_b_4_s', 'JOY_BTN4', 517, 275, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('throttle_b_5_s', 'JOY_BTN5', 732, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_4_up_s', 'JOY_BTN18', 1217, 935, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_4_down_s', 'JOY_BTN19', 1217, 1075, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_3_up_s', 'JOY_BTN16', 997, 935, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_3_down_s', 'JOY_BTN17', 997, 1075, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_2_up_s', 'JOY_BTN14', 777, 935, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_2_down_s', 'JOY_BTN15', 777, 1075, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_1_up_s', 'JOY_BTN12', 557, 935, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('toggle_1_down_s', 'JOY_BTN13', 557, 1075, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_3_up_s', 'JOY_BTN21', 1547, 405, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_3_down_s', 'JOY_BTN23', 1547, 545, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_3_left_s', 'JOY_BTN20', 1447, 475, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_3_right_s', 'JOY_BTN22', 1667, 475, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_4_up_s', 'JOY_BTN25', 1537, 935, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_4_down_s', 'JOY_BTN27', 1537, 1075, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_4_left_s', 'JOY_BTN24', 1437, 1005, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('hat_4_right_s', 'JOY_BTN26', 1657, 1005, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('switch_1_s', 'JOY_BTN6', 257, 485, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('switch_2_s', 'JOY_BTN7', 257, 647, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('switch_3_s', 'JOY_BTN8', 17, 355, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('switch_4_s', 'JOY_BTN9', 17, 535, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('switch_5_s', 'JOY_BTN10', 17, 695, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('switch_6_s', 'JOY_BTN11', 17, 865, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('thumb_button_1_s', 'JOY_BTN33', 957, 85, SIZE_STANDARD_NORMAL, 'throttle')
            self.add_control('thumb_button_2_s', 'JOY_BTN1', 977, 265, SIZE_STANDARD_NORMAL, 'throttle')

    def add_control(self, friendly_name, technical_name, x, y, size, location):
        """
        :param friendly_name:
            e.g. 'Boat Switch FWD'
        :param technical_name:
            e.g. 'JOY_BTN9'
        :param x:
            e.g. 42
        :param y:
            e.g. 899
        :param size:
            e.g. SIZE_STANDARD_NORMAL
        :param location:
            e.g. 'throttle'
        :return:
            N/A
        """
        if friendly_name[-2:] != '_s':
            self.control_mapping[technical_name] = friendly_name
            self.position_mapping[technical_name] = (x, y, size, location)
        else:
            self.control_mapping[self.switch_key + technical_name] = friendly_name
            self.switched_mapping[technical_name] = (x, y, size, location)

    def add_switch(self, control):
        if control not in self.control_mapping:
            raise Exception("Unknown switch detected - {}".format(control))
        self.switches.append(control)

    def lookup_control(self, control):
        if not control:
            return None, None
        try:
            return self.control_mapping[control], False
        except KeyError:
            try:
                return self.control_mapping[control], True
            except KeyError:
                return None, None

    def lookup_position(self, control, switched):
        if control not in self.position_mapping.keys() and not switched:
            # this control doesn't actually exist
            raise Exception("Control does not exist")
        if switched:
            return self.switched_mapping[control]
        else:
            return self.position_mapping[control]


class MongoosT50CM2:
    def __init__(self, switch_key):
        """
            Mapping of buttons to actual buttons
            # https://support.virpil.com/en/support/solutions/articles/47001250820-vpc-mongoost-50cm2-grip
                Stick
                    1    JOY_BTN1
                    2    JOY_BTN2
                    3    JOY_BTN3
                    3U   JOY_BTN_POV1_U
                    3D  JOY_BTN_POV1_D
                    3L  JOY_BTN_POV1_L
                    3R  JOY_BTN_POV1_R
                    4   JOY_BTN4
                    5   JOY_BTN5
                    6   JOY_BTN6
                    7   ...
                    8
                    9
                    10
                    11
                    12
                    13
                    14
                    15
                    16
                    17
                    18
                    19
                    20
                    21
                    22
                    23
                    24
                    25
                    26
                    27
                    28

        """
        self.name = 'mongoosT_50cm2'
        self.controller_type = 'hotas'
        self.ignore_mapping = {
            'JOY_Z',
            'JOY_Y',
            'JOY_X',
            'JOY_RZ',
            'JOY_RY',
            'JOY_RX',
        }
        self.switches = []
        self.stick_file = f'virpil_stick.png'
        self.render_stick = True
        self.render_throttle = False

        self.switch_key = switch_key

        self.control_mapping = {}
        self.position_mapping = {}
        self.switched_mapping = {}

        # to determine these numbers, add two to the left value and five to the top value
        self.add_control('JOY_BTN1', 'JOY_BTN1', 935, 545, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN2', 'JOY_BTN2', 935, 600, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN3', 'JOY_BTN3', 235, 310, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN_POV1_U', 'JOY_BTN_POV1_U', 235, 255, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN_POV1_D', 'JOY_BTN_POV1_D', 235, 360, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN_POV1_L', 'JOY_BTN_POV1_L', 90, 310, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN_POV1_R', 'JOY_BTN_POV1_R', 380, 310, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN4', 'JOY_BTN4', 380, 90, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN5', 'JOY_BTN5', 755, 90, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN6', 'JOY_BTN6', 755, 35, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN7', 'JOY_BTN7', 900, 90, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN8', 'JOY_BTN8', 755, 145, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN9', 'JOY_BTN9', 615, 90, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN10', 'JOY_BTN10', 930, 200, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN11', 'JOY_BTN11', 235, 500, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN12', 'JOY_BTN12', 235, 450, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN13', 'JOY_BTN13', 380, 500, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN14', 'JOY_BTN14', 235, 555, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN15', 'JOY_BTN15', 90, 500, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN16', 'JOY_BTN16', 930, 310, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN17', 'JOY_BTN17', 1115, 260, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN18', 'JOY_BTN18', 1115, 200, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN19', 'JOY_BTN19', 1115, 310, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN20', 'JOY_BTN20', 935, 450, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN28', 'JOY_BTN28', 935, 395, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN21', 'JOY_BTN21', 790, 745, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN22', 'JOY_BTN22', 790, 695, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN23', 'JOY_BTN23', 935, 750, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN24', 'JOY_BTN24', 790, 800, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN25', 'JOY_BTN25', 645, 750, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN26', 'JOY_BTN26', 930, 865, SIZE_VIRPIL_SMALL, 'stick')
        self.add_control('JOY_BTN27', 'JOY_BTN27', 755, 450, SIZE_VIRPIL_SMALL, 'stick')

        # Switched
        """
        if switch_key:
            self.add_control('JOY_BTN1_s', 'JOY_BTN1_s', 122, 255, SIZE_STANDARD_NORMAL, 'stick')
        """

    def add_control(self, friendly_name, technical_name, x, y, size, location):
        """
        :param friendly_name:
            e.g. 'Boat Switch FWD'
        :param technical_name:
            e.g. 'JOY_BTN9'
        :param x:
            e.g. 42
        :param y:
            e.g. 899
        :param size:
            e.g. SIZE_STANDARD_NORMAL
        :param location:
            e.g. 'throttle'
        :return:
            N/A
        """
        if friendly_name[-2:] != '_s':
            self.control_mapping[technical_name] = friendly_name
            self.position_mapping[technical_name] = (x, y, size, location)
        else:
            self.control_mapping[self.switch_key + technical_name] = friendly_name
            self.switched_mapping[technical_name] = (x, y, size, location)

    def add_switch(self, control):
        if control not in self.control_mapping:
            raise Exception("Unknown switch detected - {}".format(control))
        self.switches.append(control)

    def lookup_control(self, control):
        if not control:
            return None, None
        try:
            return self.control_mapping[control], False
        except KeyError:
            try:
                return self.control_mapping[control], True
            except KeyError:
                return None, None

    def lookup_position(self, control, switched):
        if control not in self.position_mapping.keys() and not switched:
            # this control doesn't actually exist
            raise Exception("Control does not exist")
        if switched:
            return self.switched_mapping[control]
        else:
            return self.position_mapping[control]


class MT50CM3:
    def __init__(self, switch_key):
        """
                Mapping of buttons to actual buttons
                Coolie Switch Up    JOY_BTN_POV1_U
                Coolie Switch Down  JOY_BTN_POV1_D
                Coolie Switch Left  JOY_BTN_POV1_L
                Coolie Switch Right JOY_BTN_POV1_R
                Mic Switch FWD      JOY_BTN4
                Mic Switch AFT      JOY_BTN6
                Mic Switch LEFT     JOY_BTN3
                Mic Switch RIGHT    JOY_BTN5
                SPEEDBRAKE OUT      JOY_BTN7
                SPEEDBRAKE IN       JOY_BTN8
                Boat switch FWD     JOY_BTN9
                Boat Switch AFT     JOY_BTN10
                China Hat FWD       JOY_BTN11
                China Hat AFT       JOY_BTN12
                Throttle Button     JOY_BTN15
                Pinkie Switch FWD   JOY_BTN13
                Pinkie Swift AFT    JOY_BTN14
                FLAPS UP            JOY_BTN22
                FLAPS DWN           JOY_BTN23

                EAC                 JOY_BTN24
                RDR ALTM            JOY_BTN25
                AP                  JOY_BTN26
                LASTE / PATH        JOY_BTN27
                LASTE / ALT         JOY_BTN28
                L/G WRN             JOY_BTN21
                flaps up            JOY_BTN22
                flaps down          JOY_BTN23
                APU start           JOY_BTN20
                IGN L               JOY_BTN18 | JOY_BTN31
                IGN R               JOY_BTN19 | JOY_BTN32
                ENG FLOW L          JOY_BTN16
                ENG FLOW R          JOY_BTN17
                Note - slew press is not covered currently
        """
        self.name = 'virpil_throttle'
        self.controller_type = 'hotas'
        self.ignore_mapping = {}
        self.switches = []
        self.throttle_file = 'virpil_throttle.png'
        self.render_stick = False
        self.render_throttle = True

        self.switch_key = switch_key
        self.control_mapping = {}
        self.position_mapping = {}
        self.switched_mapping = {}
        # 38-43 = 56-61
        self.add_control('JOY_BTN1', 'JOY_BTN1', 75, 170, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN2', 'JOY_BTN2', 75, 115, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN3', 'JOY_BTN3', 75, 220, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN4', 'JOY_BTN4', 75, 320, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN5', 'JOY_BTN5', 220, 425, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN6', 'JOY_BTN6', 220, 380, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN7', 'JOY_BTN7', 220, 320, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN8', 'JOY_BTN8', 830, 170, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN9', 'JOY_BTN9', 830, 120, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN10', 'JOY_BTN10', 980, 170, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN11', 'JOY_BTN11', 830, 225, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN12', 'JOY_BTN12', 695, 170, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN13', 'JOY_BTN13', 1190, 130, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN14', 'JOY_BTN14', 765, 375, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN15', 'JOY_BTN15', 765, 430, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN16', 'JOY_BTN16', 1050, 300, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN17', 'JOY_BTN17', 1195, 300, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN18', 'JOY_BTN18', 1050, 355, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN19', 'JOY_BTN19', 905, 300, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN20', 'JOY_BTN20', 1050, 250, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN21', 'JOY_BTN21', 1195, 600, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN22', 'JOY_BTN22', 580, 300, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN23', 'JOY_BTN23', 580, 350, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN24', 'JOY_BTN24', 435, 300, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN25', 'JOY_BTN25', 580, 245, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN26', 'JOY_BTN26', 720, 300, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN27', 'JOY_BTN27', 1050, 480, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN28', 'JOY_BTN28', 1050, 535, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN29', 'JOY_BTN29', 905, 480, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN30', 'JOY_BTN30', 1050, 425, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN31', 'JOY_BTN31', 1190, 480, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN32', 'JOY_BTN32', 575, 425, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN33', 'JOY_BTN33', 1045, 615, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN34', 'JOY_BTN34', 575, 495, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN35', 'JOY_BTN35', 575, 570, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN36', 'JOY_BTN36', 365, 495, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN37', 'JOY_BTN37', 365, 550, SIZE_VIRPIL_SMALL, 'throttle')

        # labeled in the image as 38-43 but actually 56-61
        self.add_control('JOY_BTN38', 'JOY_BTN56', 900, 725, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN39', 'JOY_BTN57', 1050, 725, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN40', 'JOY_BTN58', 1195, 725, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN41', 'JOY_BTN59', 900, 780, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN42', 'JOY_BTN60', 1050, 780, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN43', 'JOY_BTN61', 1195, 780, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN44', 'JOY_BTN44', 75, 610, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN45', 'JOY_BTN45', 75, 665, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN46', 'JOY_BTN46', 220, 610, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN47', 'JOY_BTN47', 220, 665, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN48', 'JOY_BTN48', 365, 610, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN49', 'JOY_BTN49', 365, 665, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN50', 'JOY_BTN50', 150, 810, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN51', 'JOY_BTN51', 150, 870, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN52', 'JOY_BTN52', 150, 760, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_BTN53', 'JOY_BTN53', 290, 810, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN54', 'JOY_BTN54', 290, 870, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_BTN55', 'JOY_BTN55', 290, 760, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_RX', 'JOY_RX', 120, 30, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_RY', 'JOY_RY', 550, 30, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_X', 'JOY_X', 1170, 185, SIZE_VIRPIL_SMALL, 'throttle')
        self.add_control('JOY_Y', 'JOY_Y', 1170, 80, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_RZ', 'JOY_RZ', 880, 640, SIZE_VIRPIL_SMALL, 'throttle')

        self.add_control('JOY_Z', 'JOY_Z', 340, 225, SIZE_VIRPIL_SMALL, 'throttle')
        # Switched
        """
        if switch_key:
            self.add_control('mic_switch_fwd_s', 'JOY_BTN4', 572, 15, SIZE_STANDARD_NORMAL, 'throttle')
        """

    def add_control(self, friendly_name, technical_name, x, y, size, location):
        """
        :param friendly_name:
            e.g. 'Boat Switch FWD'
        :param technical_name:
            e.g. 'JOY_BTN9'
        :param x:
            e.g. 42
        :param y:
            e.g. 899
        :param size:
            e.g. SIZE_STANDARD_NORMAL
        :param location:
            e.g. 'throttle'
        :return:
            N/A
        """
        if friendly_name[-2:] != '_s':
            self.control_mapping[technical_name] = friendly_name
            self.position_mapping[technical_name] = (x, y, size, location)
        else:
            self.control_mapping[self.switch_key + technical_name] = friendly_name
            self.switched_mapping[technical_name] = (x, y, size, location)

    def add_switch(self, control):
        if control not in self.control_mapping:
            raise Exception("Unknown switch detected - {}".format(control))
        self.switches.append(control)

    def lookup_control(self, control):
        if not control:
            return None, None
        try:
            return self.control_mapping[control], False
        except KeyError:
            try:
                return self.control_mapping[control], True
            except KeyError:
                return None, None

    def lookup_position(self, control, switched):
        if control not in self.position_mapping.keys() and not switched:
            # this control doesn't actually exist
            raise Exception("Control does not exist")
        if switched:
            return self.switched_mapping[control]
        else:
            return self.position_mapping[control]
