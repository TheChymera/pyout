"""Terminal styling for tabular data.

TODO: Come up with a better one-line description.  Should emphasize
style declaration.
"""

__version__ = "0.1.0"
__all__ = ["Tabular"]

from collections import OrderedDict
from contextlib import contextmanager
from blessings import Terminal


class Field(object):
    """Format, process, and render tabular fields.

    A Field instance is a template for a string that is defined by its
    width, text alignment, and its "processors".  When a field is
    called with a value, it renders the value as a string with the
    specified width and text alignment.  Before this string is
    returned, it is passed through the chain of processors.  The
    rendered string is the result returned by the last processor.

    Parameters
    ----------
    width : int
    align : {'left', 'right', 'center'}

    Attributes
    ----------
    width : int
    align : str
    processors : dict
        Each key maps to a list of processors.  The keys "core" and
        "default" must always be present.  When an instance object is
        called, the rendered result is always sent through the "core"
        processors.  It will then be sent through the "default"
        processors unless another key is provided as the optional
        `which` argument.

        A processor should take two positional arguments, the value
        that is being rendered and the current result.  Its return
        value will be passed to the next processor as the current
        result.
    """

    _align_values = {"left": "<", "right": ">", "center": "^"}

    def __init__(self, width=10, align="left"):
        self._width = width
        self._align = align
        self._fmt = self._build_format()

        self.processors = {"core": [], "default": []}

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        self._width = value
        self._fmt = self._build_format()

    @property
    def align(self):
        return self._align

    @align.setter
    def align(self, value):
        self._align = value
        self._fmt = self._build_format()

    def _build_format(self):
        align = self._align_values[self.align]
        return "".join(["{:", align, str(self.width), "}"])

    def __call__(self, value, which="default"):
        """Render `value` by feeding it through the processors.

        Parameters
        ----------
        value : str
        which : str, optional
            A key for the `processors` attribute that indicates the
            list of processors to use in addition to the "core" list.
        """
        result = self._fmt.format(value)
        for fn in self.processors["core"] + self.processors[which]:
            result = fn(value, result)
        return result


class StyleProcessors(object):
    """A base class for generating Field.processors for styled output.

    Attributes
    ----------
    style_keys : list of tuples
        Each pair consists of a style attribute (e.g., "bold") and the
        expected type.
    """

    style_keys = [("bold", bool),
                  ("underline", bool),
                  ("color", str)]

    def translate(self, name):
        """Translate a style key for a given output type.

        Parameters
        ----------
        name : str
            A style key (e.g., "bold").

        Returns
        -------
        An output-specific translation of `name`.
        """
        raise NotImplementedError

    def by_key(self, key):
        """Return a processor for the style given by `key`.

        Parameters
        ----------
        key : str
            A style key to be translated.

        Returns
        -------
        A function.
        """
        def by_key_fn(_, result):
            return self.translate(key) + result
        return by_key_fn

    def by_lookup(self, mapping):
        """Return a processor that extracts the style from `mapping`.

        Parameters
        ----------
        mapping : mapping
            A map from the field value to a style key.

        Returns
        -------
        A function.
        """
        def by_lookup_fn(value, result):
            try:
                return self.translate(mapping[value]) + result
            except KeyError:
                return result
        return by_lookup_fn

    def by_lookup_cond(self, mapping, key):
        """Conditionally return a processor for the style given by `key`.

        Parameters
        ----------
        mapping : mapping
            A map from the field value to a value that indicates
            whether the processor should style its result.
        key : str
            A style key to be translated.

        Returns
        -------
        A function.
        """
        def by_lookup_cond_fn(value, result):
            try:
                if mapping[value]:
                    return self.translate(key) + result
            except KeyError:
                return result
            return result
        return by_lookup_cond_fn

    def by_interval_lookup(self, intervals):
        """Return a processor that extracts the style from `intervals`.

        Parameters
        ----------
        intervals : sequence of tuples
            Each tuple should have the form `(start, end, key)`, where
            start is the start of the interval (inclusive) , end is
            the end of the interval, and key is a style key.

        Returns
        -------
        A function.
        """
        def by_interval_lookup_fn(value, result):
            value = float(value)
            for start, end, key in intervals:
                if start is None:
                    start = float("-inf")
                elif end is None:
                    end = float("inf")

                if start <= value < end:
                    return self.translate(key) + result
            return result
        return by_interval_lookup_fn

    def from_style(self, column_style):
        """Yield processors based on `column_style`.

        Parameters
        ----------
        column_style : dict
            A style where the top-level keys correspond to style
            attributes such as "bold" or "color".

        Returns
        -------
        A generator object.
        """
        for key, key_type in self.style_keys:
            if key not in column_style:
                continue
            if key_type is bool:
                if column_style[key] is True:
                    yield self.by_key(key)
                else:
                    try:
                        column_style[key][0] == "label"
                    except TypeError:
                        continue
                    else:
                        yield self.by_lookup_cond(column_style[key][1], key)
            elif key_type is str:
                if column_style[key][0] == "label":
                    yield self.by_lookup(column_style[key][1])
                elif column_style[key][0] == "interval":
                    yield self.by_interval_lookup(column_style[key][1])
                else:
                    yield self.by_key(column_style[key])


class TermProcessors(StyleProcessors):
    """Generate Field.processors for styled Terminal output.

    Parameters
    ----------
    term : blessings.Terminal
    """

    def __init__(self, term):
        self.term = term

    def translate(self, name):
        """Translate a style key into a Terminal code.

        Parameters
        ----------
        name : str
            A style key (e.g., "bold").

        Returns
        -------
        An output-specific translation of `name` (e.g., "\x1b[1m").
        """
        return str(getattr(self.term, name))

    def _maybe_reset(self):
        def maybe_reset_fn(_, result):
            if "\x1b" in result:
                return result + self.term.normal
            return result
        return maybe_reset_fn

    def from_style(self, column_style):
        """Call StyleProcessors.from_style, adding a Terminal-specific reset.
        """
        for proc in super(TermProcessors, self).from_style(column_style):
            yield proc
        yield self._maybe_reset()


def _adopt(style, new_style):
    if new_style is None:
        return style
    return {key: dict(style[key], **new_style.get(key, {})) for key in style}


def _safe_get(mapping, key, default=None):
    try:
        return mapping.get(key, default)
    except AttributeError:
        return default


class Tabular(object):
    """Interface for writing and updating styled terminal output.

    Parameters
    ----------
    columns : list of str or OrderedDict, optional
        Column names.  An OrderedDict can be used instead of a
        sequence to provide a map of short names to the displayed
        column names.

        If not given, the keys will be extracted from the first row of
        data that the object is called with, which is particularly
        useful if the row is an OrderedDict.  This argument must be
        given if this instance will be called with a sequence rather
        than a dictionary.
    style : dict, optional
        Each top-level key should be a column name and the value
        should be a style dict that overrides the `default_style`
        class attribute.  See the "Examples" section below.
    stream : file object, optional
        Defaults to standard output.

    force_styling : bool or None
        Passed to blessings.Terminal.

    Attributes
    ----------
    term : blessings.Terminal instance

    Examples
    --------

    Create a `Tabular` instance for two output fields, "name" and
    "status".

    >>> out = Tabular(["name", "status"], style={"status": {"width": 5}})

    The first field, "name", is taken as the unique ID.  The `style`
    argument is used to override the default width for the "status"
    field that is defined by the class attribute `default_style`.

    Write a row to stdout:

    >>> out({"name": "foo", "status": "OK"})

    Write another row, overriding the style:

    >>> out({"name": "bar", "status": "BAD"},
    ...     style={"status": {"color": "red", "bold": True}})
    """

    # TODO: Support things like auto-width, value-based coloring, etc.
    default_style = {"align": "left",
                     "width": 10}

    _header_attributes = {"align", "width"}

    def __init__(self, columns=None, style=None, stream=None, force_styling=False):
        self.term = Terminal(stream=stream, force_styling=force_styling)
        self._tproc = TermProcessors(self.term)

        self._rows = []
        self._columns = columns
        self._fields = None

        self._init_style = style
        self._style = None
        self._header_style = None

        self._autowidth_columns = set()
        self._update_previous = False

        if columns is not None:
            self._setup_style()
            self._setup_fields()

    def _setup_style(self):
        self._style = _adopt({c: self.default_style for c in self._columns},
                             self._init_style)

        if self._init_style is not None and "header_" in self._init_style:
            self._header_style = {}
            for col in self._columns:
                cstyle = {k: v for k, v in self._style[col].items()
                          if k in self._header_attributes}
                self._header_style[col] = dict(cstyle,
                                               **self._init_style["header_"])

    def _setup_fields(self):
        self._fields = {}
        for column in self._columns:
            cstyle = self._style[column]

            style_width = cstyle["width"]
            if style_width == "auto":
                width = 1
                self._autowidth_columns.add(column)
            else:
                width = style_width

            field = Field(width=width, align=cstyle["align"])
            field.processors["default"] = list(self._tproc.from_style(cstyle))

            self._fields[column] = field

    _preformat_method = lambda self, x: x

    def _seq_to_dict(self, row):
        return dict(zip(self._columns, row))

    def _writerow(self, row, style=None, adopt=True):
        fields = self._fields

        if style is not None:
            rowstyle = _adopt(self._style, style) if adopt else style
            for column, cstyle in rowstyle.items():
                fields[column].processors["row"] = list(
                    self._tproc.from_style(cstyle))
            proc_key = "row"
        else:
            proc_key = "default"

        row = self._preformat_method(row)

        for column in self._columns:
            if column in self._autowidth_columns:
                value_width = len(str(row[column]))
                if value_width > self._fields[column].width:
                    self._fields[column].width = value_width
                    self._update_previous = True

        try:
            proc_fields = [fields[c](row[c], proc_key) for c in self._columns]
        except TypeError:
            if self._preformat_method == self._seq_to_dict:
                raise
            self._preformat_method = self._seq_to_dict
            self._writerow(row, style, adopt=False)
        else:
            self.term.stream.write(" ".join(proc_fields) + "\n")

    def _maybe_write_header(self):
        if self._header_style is not None:
            if self._preformat_method == self._seq_to_dict:
                row = self._columns
            else:
                if isinstance(self._columns, OrderedDict):
                    row = self._columns
                else:
                    row = dict(zip(self._columns, self._columns))
            self._writerow(row, style=self._header_style, adopt=False)

    def __call__(self, row, style=None):
        """Write styled `row` to the terminal.

        Parameters
        ----------
        row : dict or sequence
            A dictionary where keys are the column names and values
            are the data to write.  Otherwise, row is treated as a
            sequence that follows the same order as the constructor's
            `columns` argument.
        style : dict, optional
            Each top-level key should be a column name and the value
            should be a style dict that overrides the class instance
            style.
        """
        if self._columns is None:
            self._columns = self._infer_columns(row)
            self._setup_style()
            self._setup_fields()

        if not self._rows:
            self._maybe_write_header()
        self._rows.append(row)
        self._writerow(row, style=style)

        if self._update_previous:
            ## TODO: Try to make this code clearer by moving terminal
            ## logic into helpers.
            previous = self._rows[:-1]
            if previous or self._header_style is not None:
                self._move_to_firstrow()
                self.term.stream.write(self.term.clear_eol)
                self._maybe_write_header()
                for prev_row in previous:
                    self.term.stream.write(self.term.clear_eol)
                    self._writerow(prev_row)
                self.term.stream.write(self.term.move_down)
            self._update_previous = False

    @staticmethod
    def _infer_columns(row):
        try:
            return list(row.keys())
        except AttributeError:
            raise ValueError("Can't infer columns from data")

    def _repaint(self):
        ## TODO: I don't think this is a good approach.  Destroys any
        ## scroll back.
        self.term.stream.write(self.term.clear)
        self._maybe_write_header()
        for row in self._rows:
            self._writerow(row)
        self.term.stream.flush()

    def _move_to_firstrow(self):
        ntimes = len(self._rows) + (self._header_style is not None)
        self.term.stream.write(self.term.move_up * ntimes)

    @contextmanager
    def _moveback(self, n):
        self.term.stream.write(self.term.move_up * n + self.term.clear_eol)
        try:
            yield
        finally:
            self.term.stream.write(self.term.move_down * (n - 1))
            self.term.stream.flush()

    ## FIXME: This will break with stderr and when the output scrolls.
    ## Maybe we could check term height and repaint?
    def rewrite(self, ids, column, new_value, style=None):
        """Rewrite a row.

        Parameters
        ----------
        ids : dict
            The keys are the column names that in combination uniquely
            identify a row when matched for the values.
        column : str
            The name of the column whose value should be updated to
            `new_value`.
        new_value : str
        style : dict
            A new style dictionary to use for the new row.  All
            unspecified style elements are taken from the instance's
            `style`.
        """
        nback = None
        for rev_idx, row in enumerate(reversed(self._rows), 1):
            if all(row[k] == v for k, v in ids.items()):
                nback = rev_idx
                break
        if nback is None:
            raise ValueError("Could not find row for {}".format(ids))

        idx = len(self._rows) - nback
        self._rows[idx][column] = new_value

        with self._moveback(nback):
            self._writerow(self._rows[idx], style)
