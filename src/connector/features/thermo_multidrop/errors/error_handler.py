# import functools
# import inspect

# from .device_errors import InvalidStateError, NoCartridgeError, UnavailableError
# from .serial_errors import ReadError, SerialConnectionError, WriteError
#

# def error_handler(func):
#     """
#     Decorator to handle the errors raised in the io layer.
#     """
#
#     if inspect.iscoroutinefunction(func):
#
#         async def wrapper(self, *args, **kwargs):
#             try:
#                 return await func(self, *args, **kwargs)
#             except RuntimeError as error:
#                 error_helper(error)
#
#     else:
#
#         async def wrapper(self, *args, **kwargs):
#             try:
#                 async for item in func(self, *args, **kwargs):
#                     yield item
#             except RuntimeError as error:
#                 error_helper(error)
#
#     return functools.wraps(func)(wrapper)
#
#
# def error_helper(error):
#     """Determine the error type and raise the corresponding sila error."""
#     if isinstance(error, RuntimeError):
#         if "Calibration in progress" in str(error):
#             raise InvalidStateError from error
#         if "Connection error" in str(error):
#             raise SerialConnectionError from error
#         if "Write error" in str(error):
#             raise WriteError from error
#         if "Read error" in str(error):
#             raise ReadError from error
#         if "Sensor readouts are unavailable during heat up" in str(error):
#             raise InvalidStateError(description=str(error)) from error
#     if isinstance(error, ValueError):
#         if "This command is not available" in str(error):
#             raise UnavailableError from error
#         if "No cartridge detected" in str(error):
#             raise NoCartridgeError from error
#         if "Unexpected read" in str(error):
#             raise ReadError from error
