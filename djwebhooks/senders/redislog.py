# -*- coding: utf-8 -*-
"""djwebhooks.senders.orm.sender
Decorator for 'hooking' a payload request to a foreign URL using
`djwebhooks.senders.orm.sender`. A payload request is generated by the hooked
function, which must return a JSON-serialized value.

Note: Thanks to json232, the JSON-serialized data can include DateTime objects.

    :event: The name of the event as defined in settings.WEBHOOK_EVENTS
    :owner: Required for the payload function. This represents the user who
        created or manages the event. Is not normally request.user.

Decorator Usage:

    # Define the payload function!
    @hook(event="order.ship")
    def order_ship(order, owner):
        return {
            "order_num": order.order_num,
            "shipping_address": order.shipping_address,
            "line_items": [x.sku for x in order.lineitem_set.all()]
        }

    # Call the payload function!
    def order_confirmation(request, order_num):
        order = get_object_or_404(Order, order_num=order_num)
        if order.is_valid():
            order_ship(order=order, owner=order.merchant)

        return redirect("home")
"""

from django.conf import settings

from webhooks.senders.base import Senderable

from ..models import WebhookTarget

# For use with custom user models, this lets you define the owner field on a model
WEBHOOK_OWNER_FIELD = getattr(settings, "WEBHOOK_OWNER_FIELD", "username")

# List the attempts as an iterable of integers.
#   Each number represents the amount of time to be slept between attempts
#   The first number should always be 0 so no time is wasted.
WEBHOOK_ATTEMPTS = getattr(settings, "WEBHOOK_EVENTS", (0, 15, 30, 60))


class RedisLogSenderable(Senderable):

    def notify(self, message):
        """
            TODO: Add code to lpush to redis stack
                    rpop when stack hits size 'X'
        """

        pass


def redislog_callable(wrapped, dkwargs, hash_value=None, *args, **kwargs):
    """
        This is a synchronous sender callable that uses the Django ORM to store
            webhooks and Redis for the delivery log.

        dkwargs argument requires the following key/values:

            :event: A string representing an event.

        kwargs argument requires the following key/values

            :owner: The user who created/owns the event
    """

    if "event" not in dkwargs:
        msg = "djwebhooks.decorators.hook requires an 'event' argument in the decorator."
        raise TypeError(msg)
    event = dkwargs['event']

    if "owner" not in kwargs:
        msg = "djwebhooks.senders.redislog_callable requires an 'owner' argument in the decorated function."
        raise TypeError(msg)
    owner = kwargs['owner']

    if "identifier" not in kwargs:
        msg = "djwebhooks.senders.redislog_callable requires an 'identifier' argument in the decorated function."
        raise TypeError(msg)
    identifier = kwargs['identifier']

    senderobj = RedisLogSenderable(
            wrapped, dkwargs, hash_value, WEBHOOK_ATTEMPTS, *args, **kwargs
    )

    # Add the webhook object just so it's around
    # TODO - error handling if this can't be found
    try:
        senderobj.webhook_target = WebhookTarget.objects.get(
            event=event,
            owner=owner,
            identifier=identifier
        )
    except WebhookTarget.DoesNotExist:
        return {"error": "WebhookTarget not found"}

    # Get the target url and add it
    senderobj.url = senderobj.webhook_target.target_url

    # Get the payload. This overides the senderobj.payload property.
    senderobj.payload = senderobj.get_payload()

    # Get the creator and add it to the payload.
    senderobj.payload['owner'] = getattr(kwargs['owner'], WEBHOOK_OWNER_FIELD)

    # get the event and add it to the payload
    senderobj.payload['event'] = dkwargs['event']

    return senderobj.send()
