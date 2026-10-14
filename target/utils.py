import os
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings

# As in target.py: the font ships with the app, so read it from the app's
# own static directory rather than from a collected STATIC_ROOT.
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "static", "target", "fonts")

def saveTargetImage(letters, pk):
    height = 300
    width = 300
    image = Image.new(mode='L', size=(height, width), color=255)

    draw = ImageDraw.Draw(image)

    x = 0
    y_start = 0
    y_end = image.height
    line = ((x, y_start), (x, y_end))
    draw.line(line, fill=128)
    x = image.width / 3
    y_start = 0
    y_end = image.height
    line = ((x, y_start), (x, y_end))
    draw.line(line, fill=128)
    x = x + image.width / 3
    line = ((x, y_start), (x, y_end))
    draw.line(line, fill=128)
    x = image.width - 1
    line = ((x, y_start), (x, y_end))
    draw.line(line, fill=128)


    y = 0
    x_start = 0
    x_end = image.width
    line = ((x_start, y), (x_end, y))
    draw.line(line, fill=128)
    y = image.height / 3
    x_start = 0
    x_end = image.width
    line = ((x_start, y), (x_end, y))
    draw.line(line, fill=128)
    y = y + image.height / 3
    line = ((x_start, y), (x_end, y))
    draw.line(line, fill=128)
    y = image.height - 1
    line = ((x_start, y), (x_end, y))
    draw.line(line, fill=128)
    x_start = image.width / 3
    y_start = image.height / 3
    x_end = x_start + image.width / 3
    y_end = y_start + image.height / 3
    area = ((x_start, y_start), (x_end, y_end))
    draw.rectangle(area, fill=0)

    font_size = int(image.height / 3 - 8)
    font = ImageFont.truetype(os.path.join(
        FONTS_DIR, "VeraMono-Bold.ttf"), font_size)
    x_start = 15
    y_start = -4

    x = x_start
    y = y_start
    _, _, w, h = draw.textbbox((0,0), letters[1])
    xy = (x + w, y,)

    draw.text(xy, letters[1], font=font)

    x = x + image.width / 3
    xy = (x + w, y)
    draw.text(xy, letters[2], font=font)

    x = x + image.width / 3
    xy = (x + w, y)
    draw.text(xy, letters[3], font=font)

    x = x_start
    y = y + image.height / 3
    xy = (x + w, y)
    draw.text(xy, letters[4], font=font)

    x = x + image.width / 3
    xy = (x + w, y)
    draw.text(xy, letters[0], fill=255, font=font)

    x = x + image.width / 3
    xy = (x + w, y,)
    draw.text(xy, letters[5], font=font)

    x = x_start
    y = y + image.height / 3
    xy = (x + w, y)
    draw.text(xy, letters[6], font=font)

    x = x + image.width / 3
    xy = (x + w, y)
    draw.text(xy, letters[7], font=font)

    x = x + image.width / 3
    xy = (x + w, y,)
    draw.text(xy, letters[8], font=font)

    # The news site kept media/targets/ on disk; create it so a fresh
    # checkout doesn't fall over on the first save.
    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'targets'), exist_ok=True)
    image.save(os.path.join(settings.MEDIA_ROOT,
                            'targets/target_' + str(pk) + '.png'))
    os.chmod(os.path.join(settings.MEDIA_ROOT,
                          'targets/target_' + str(pk) + '.png'), 0o0644)
