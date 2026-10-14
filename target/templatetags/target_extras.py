import re

from django.template.loader import render_to_string
from django import template
from django.utils.safestring import mark_safe

from target.models import Target

register = template.Library()

@register.simple_tag
def target_teaser(pk=None):
    if pk is None:
        target = Target.objects.published().latest('published')
    else:
        pk = int(pk)
        target = Target.objects.published().filter(pk=pk).first()
    return render_to_string("target/target_teaser.html",
                            {'object': target})


@register.filter
def target_rules(text):
    """Like |safe|linebreaks, except that a run of lines starting with
    "- " becomes a bulleted list, and the other lines of a paragraph run
    together. The rules on older targets are hard-wrapped mid-sentence,
    so a single newline can't be trusted to mean a line break; a blank
    line still starts a new paragraph."""
    html = []
    for para in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = para.split("\n")
        text_lines = []
        bullets = []
        for line in lines + [""]:
            if line.startswith("- "):
                bullets.append("<li>" + line[2:].strip() + "</li>")
                continue
            if bullets:
                if text_lines:
                    html.append("<p>" + " ".join(text_lines) + "</p>")
                    text_lines = []
                html.append("<ul>" + "".join(bullets) + "</ul>")
                bullets = []
            if line:
                text_lines.append(line)
        if text_lines:
            html.append("<p>" + " ".join(text_lines) + "</p>")
    return mark_safe("\n".join(html))
