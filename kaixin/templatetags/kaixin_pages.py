from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def page_url(context, param, number):
    request = context.get('request')
    if request is None:
        return f'?{param}={number}'
    query = request.GET.copy()
    query[param or 'page'] = str(number)
    encoded = query.urlencode()
    return f'?{encoded}' if encoded else '?'
