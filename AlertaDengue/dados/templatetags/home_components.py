from dados.dbdata import STATE_NAME
from django import template

register = template.Library()


@register.inclusion_tag("components/home/collapse.html", takes_context=True)
def collapse_component(context):
    context["states_name"] = STATE_NAME
    context["states_abbv"] = list(STATE_NAME.keys())

    return context


@register.inclusion_tag("components/home/carousel.html", takes_context=True)
def carousel_component(context):
    return context


@register.inclusion_tag("components/home/legend.html", takes_context=True)
def legend_component(context):
    return context