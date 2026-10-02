import datetime


def parse_date(date_str: str) -> datetime.date:
    """
    Parse a date string into a datetime.date object.

    Parameters:
      date_str: A string representing a date in the format "dd.mm.yyyy".

    Returns:
      A date object representing the parsed date.

    Example:
    parse_date("31.12.2022") -> datetime.date(2022, 12, 31)
    """

    return datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
