from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    params = context["request"].GET.copy()
    params.update(kwargs)
    return params.urlencode()
