# import asyncio
# import typing
#
# from unitelabs.cdk import sila
#
# T = typing.TypeVar("T")
#
#
# class Publisher(typing.Generic[T]):
#     def __init__(self, update: typing.Callable[[], typing.Awaitable[T]], interval: float = 5) -> None:
#         self._value: typing.Optional[T] = None
#         self._update = update
#         self._interval = interval
#
#         self.subscribers: list[asyncio.Queue[T]] = []
#         self.subscription: typing.Optional[asyncio.Task] = None
#
#     def subscribe(self) -> asyncio.Queue[T]:
#         queue = asyncio.Queue[T]()
#         if self._value is not None:
#             queue.put_nowait(self._value)
#
#         self.subscribers.append(queue)
#
#         if self.subscription is None:
#             self.subscription = sila.utils.set_interval(self.update, delay=self._interval)
#
#         return queue
#
#     def unsubscribe(self, subscription: asyncio.Queue[T]) -> None:
#         self.subscribers.remove(subscription)
#
#         if not self.subscribers:
#             if self.subscription:
#                 sila.utils.clear_interval(self.subscription)
#
#             self.subscription = None
#             self._value = None
#
#     def notify(self) -> None:
#         if self._value is not None:
#             for subscriber in self.subscribers:
#                 subscriber.put_nowait(self._value)
#
#     async def update(self) -> None:
#         self._value = await self._update()
#         self.notify()
