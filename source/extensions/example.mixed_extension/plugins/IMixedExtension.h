// Copyright (c) 2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//
#pragma once

#include <carb/Interface.h>
#include <carb/dictionary/IDictionary.h>

namespace omni
{
namespace events
{
struct EventStream;

struct Subscription
{
    EventStream* stream;
    size_t id;
};

static constexpr size_t kInvalidSubscriptionId = (size_t)-1;

using EventType = uint32_t;

using SenderId = uint32_t;


static constexpr SenderId kGlobalSenderId = 0; ///! Default sender id to use if you don't want it to be unique

struct Event
{
    EventType type; ///! Event type.
    SenderId sender; ///! Who sent an event.
    carb::dictionary::Item* payload; ///! Event payload is dictionary Item. Any data can be put into.
};

using OnEventFn = void (*)(Event* e, void* userData);


struct IEvents
{
    CARB_PLUGIN_INTERFACE("carb::events::IEvents", 0, 1)

    /**
     * Create new event stream.
     */
    EventStream*(CARB_ABI* createEventStream)();

    void(CARB_ABI* destroyEventStream)(EventStream*);

    /**
     * Subscribe to event stream. `pump`, `pop` and `try_pop` functions trigger subscriber's notification.
     * Received Event pointer is valid only in the callback itself.
     * Only events of certain event type will be received.
     */
    Subscription(CARB_ABI* subscribeToPop)(EventStream* stream, EventType eventType, OnEventFn onEvent, void* userData);

    void(CARB_ABI* unsubscribeToPop)(const Subscription& subscription);

    /**
     * Subscribe to pushing to event stream. `push` and `pushBlocked` functions trigger subscriber's notification.
     * Received Event pointer is valid only in the callback itself.
     * Only events of certain event type will be received.
     */
    Subscription(CARB_ABI* subscribeToPush)(EventStream* stream, EventType eventType, OnEventFn onEvent, void* userData);

    void(CARB_ABI* unsubscribeToPush)(const Subscription& subscription);

    /**
     * Create new event of certain type.
     */
    Event*(CARB_ABI* createEvent)(EventType eventType, SenderId sender);

    void(CARB_ABI* destroyEvent)(Event* e);

    /**
     * Get a new unique sender id.
     */
    SenderId(CARB_ABI* acquireUniqueSenderId)();

    void(CARB_ABI* releaseUniqueSenderId)(SenderId);

    /**
     * Dispatch event immediately without putting it into stream. Event ownership is not transferred.
     */
    void(CARB_ABI* dispatchEvent)(EventStream* stream, Event* e);

    /**
     * Push event into the stream. Event ownership is transferred into EventStream. You don't need to call
     * `destroyEvent()` on it.
     */
    void(CARB_ABI* pushEvent)(EventStream* stream, Event* e);

    /**
     * Push event into the stream and wait until it is dispatched by some other thread.
     */
    void(CARB_ABI* pushEventBlocked)(EventStream* stream, Event* e);

    /**
     * Get event count on a stream. The result is approximate if stream is used by multiple threads.
     */
    size_t(CARB_ABI* getEventCount)(EventStream* stream);

    /**
     * Pop event from the stream. If stream is empty this function blocks until some other thread will push an event.
     * Before popping all subscribers are triggered for this event (event is dispatched).
     * You own returned Event and responsible for calling `destroyEvent()` on it later.
     */
    Event*(CARB_ABI* popEvent)(EventStream* stream);

    /**
     * Try pop event from the stream. If stream is empty return `nullptr`.
     * Before popping all subscribers are triggered for this event (event is dispatched).
     * You own returned Event and responsible for calling `destroyEvent()` on it later.
     */
    Event*(CARB_ABI* tryPopEvent)(EventStream* stream);

    /**
     * Pump event stream.
     *
     * This function pop and destroy all event in a stream, thus dispatching them to subscribers.
     */
    void(CARB_ABI* pump)(EventStream*);
};
}
}
