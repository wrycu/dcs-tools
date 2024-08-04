from flask import Blueprint, render_template, request, send_file
from io import BytesIO
import zipfile

kneeboard = Blueprint('kneeboard', __name__, url_prefix='/kneeboard')


@kneeboard.route('/')
def landing():
    return render_template('kneeboard/upload.html')


@kneeboard.route('/', methods=['POST'])
def upload():
    filenames = [x for x in request.files]
    # pull the mission file from the POST data
    uploaded_files = []
    for cur_file in filenames:
        if '.miz' in request.files[cur_file].filename:
            uploaded_files.append(request.files[cur_file])
    if not uploaded_files:
        return 'No miz file found', 400
    # check for images
    image_files = []
    for cur_file in filenames:
        if '.miz' not in request.files[cur_file].filename:
            image_files.append(request.files[cur_file])
    if not image_files:
        return 'No kneeboard images found', 400
    parser = InMemoryZip(uploaded_files[0].read())
    for cur_file in image_files:
        parser.append('KNEEBOARD\\IMAGES\\' + cur_file.filename, cur_file.read())
    return send_file(BytesIO(parser.read()), download_name='test.miz', as_attachment=True, mimetype='application/zip')


class InMemoryZip(object):
    def __init__(self, miz):
        # Create the in-memory file-like object for working w/IMZ
        self.in_memory_zip = BytesIO(miz)

    # Just zip it, zip it
    def append(self, filename_in_zip, file_contents):
        # Appends a file with name filename_in_zip and contents of
        # file_contents to the in-memory zip.
        # Get a handle to the in-memory zip in append mode
        zf = zipfile.ZipFile(self.in_memory_zip, "a", zipfile.ZIP_DEFLATED, False)

        # Write the file to the in-memory zip
        zf.writestr(filename_in_zip, file_contents)

        # Mark the files as having been created on Windows so that
        # Unix permissions are not inferred as 0000
        for zfile in zf.filelist:
            zfile.create_system = 0

        return self

    def read(self):
        # Returns a string with the contents of the in-memory zip.
        self.in_memory_zip.seek(0)
        return self.in_memory_zip.read()

    # Zip it, zip it, zip it
    def writetofile(self, filename):
        # Writes the in-memory zip to a physical file.
        with open(filename, "wb") as file:
            file.write(self.read())
