# STDLIB
import os
import pathlib
import re
import sys
from types import TracebackType
from typing import Any, List, Optional, Tuple, Type, Union

# EXT
import attr

PathLikeOrString = Union[str, "os.PathLike[Any]"]
__all__ = ("IgnoreParser",)


@attr.s(auto_attribs=True)
class IgnoreRule(object):
    pattern: str
    regex: str
    negation: bool
    directory_only: bool
    anchored: bool
    base_path: pathlib.Path
    source: Optional[Tuple[pathlib.Path, int]]

    def match(self, abs_path: pathlib.Path) -> bool:
        matched = False
        try:
            rel_path = str(abs_path.resolve().relative_to(self.base_path))
        except ValueError:
            return False
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
        if re.search(self.regex, rel_path):
            matched = True
        return matched


# IgnoreParser{{{
class IgnoreParser(object):
    def __init__(self) -> None:
        """
        init the igittigitt parser.
        """
        # IgnoreParser}}}

        self.rules: List[IgnoreRule] = list()
        # if the rules contain a negation rule
        self.rules_contains_negation_rule: bool = False
        # small optimization - we have a
        # good chance that the last rule
        # might match again
        self.last_matching_rule: Optional[IgnoreRule] = None

    def __call__(self,) -> None:
        self.__init__()  # type: ignore

    def __enter__(self) -> "IgnoreParser":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        pass

    def parse_rule_file(
        self, rule_file: PathLikeOrString, base_dir: Optional[PathLikeOrString] = None,
    ) -> None:
        """
        parse a git ignore file, create rules from a gitignore file

        Parameter
        ---------
        full_path
            the full path to the ignore file
        base_dir
            optional base dir, for testing purposes only.
            the base dir is the parent of the rule file,
            because rules are relative to the directory
            were the rule file resides

        """
        if isinstance(rule_file, str):
            path_rule_file = pathlib.Path(rule_file).resolve()
        elif isinstance(rule_file, pathlib.Path):
            path_rule_file = rule_file.resolve()
        else:
            raise TypeError('wrong type for "rule_file"')

        if base_dir is None:
            path_base_dir = path_rule_file.parent
        elif isinstance(base_dir, str):
            path_base_dir = pathlib.Path(base_dir).resolve()
        elif isinstance(base_dir, pathlib.Path):
            path_base_dir = base_dir.resolve()
        else:
            raise TypeError('wrong type for "base_dir"')

        with open(path_rule_file) as ignore_file:
            counter = 0
            for line in ignore_file:
                counter += 1
                line = line.rstrip("\n")
                rule = rule_from_pattern(
                    line, base_path=path_base_dir, source=(path_rule_file, counter),
                )
                if rule:
                    self.rules.append(rule)
                    if rule.negation:
                        self.rules_contains_negation_rule = True

    # add_rule{{{
    def add_rule(self, pattern: str, base_path: PathLikeOrString) -> None:
        """
        add a rule as a string

        Parameter
        ---------
        pattern
            the pattern
        base_path
            since gitignore patterns are relative to a base
            directory, that needs to be provided here
        """
        # add_rule}}}

        path_base_path = pathlib.Path(base_path).resolve()

        rule = rule_from_pattern(pattern, path_base_path)
        if rule:
            self.rules.append(rule)
            if rule.negation:
                self.rules_contains_negation_rule = True

    def match(self, file_path: PathLikeOrString) -> bool:
        path_file_path = pathlib.Path(file_path)
        if self.rules_contains_negation_rule:
            return self._match_with_negations(path_file_path)
        else:
            return self._match_without_negations(path_file_path)

    def _match_with_negations(self, path_file_path: pathlib.Path) -> bool:
        """
        match with negotiations - in that case we need to check
        every single rule, because there can be a match,
        followed by an unmatch.
        """
        matched = False
        for rule in self.rules:
            if rule.match(path_file_path):
                if rule.negation:
                    matched = False
                else:
                    matched = True
        return matched

    def _match_without_negations(self, path_file_path: pathlib.Path) -> bool:
        """
        match without negotiations - in that case we can return
        immediately after a match.
        """

        # small optimisation - we have a good chance
        # that the last rule can match again
        if self.last_matching_rule and self.last_matching_rule.match(path_file_path):
            return True

        for rule in self.rules:
            if rule.match(path_file_path):
                self.last_matching_rule = rule
                return True
        return False


def rule_from_pattern(
    pattern: str,
    base_path: pathlib.Path,
    source: Optional[Tuple[pathlib.Path, int]] = None,
) -> Optional[IgnoreRule]:
    """
     Take a .gitignore match pattern, such as "*.py[cod]" or "**/*.bak",
    and return an IgnoreRule suitable for matching against files and
    directories. Patterns which do not match files, such as comments
    and blank lines, will return None.
    Because git allows for nested .gitignore files, a base_path value
    is required for correct behavior. The base path should be absolute.
    """
    if not base_path.is_absolute():
        raise ValueError("base_path must be absolute")
    # Store the exact pattern for our repr and string functions
    orig_pattern = pattern
    # Early returns follow
    # Discard comments and separators
    if pattern.strip() == "" or pattern[0] == "#":
        return None
    # Discard anything with more than two consecutive asterisks
    if pattern.find("***") > -1:
        return None
    # Strip leading bang before examining double asterisks
    if pattern[0] == "!":
        negation = True
        pattern = pattern[1:]
    else:
        negation = False
    # Discard anything with invalid double-asterisks -- they can appear
    # at the start or the end, or be surrounded by slashes
    for m in re.finditer(r"\*\*", pattern):
        start_index = m.start()
        if (
            start_index != 0
            and start_index != len(pattern) - 2
            and (pattern[start_index - 1] != "/" or pattern[start_index + 2] != "/")
        ):
            return None

    # Special-casing '/', which doesn't match any files or directories
    if pattern.rstrip() == "/":
        return None

    directory_only = pattern[-1] == "/"
    # A slash is a sign that we're tied to the base_path of our rule
    # set.
    anchored = "/" in pattern[:-1]
    if pattern[0] == "/":
        pattern = pattern[1:]
    if pattern[0] == "*" and len(pattern) >= 2 and pattern[1] == "*":
        pattern = pattern[2:]
        anchored = False
    if pattern[0] == "/":
        pattern = pattern[1:]
    if pattern[-1] == "/":
        pattern = pattern[:-1]
    if pattern[0] == "\\" and pattern[1] == "#":
        pattern = pattern[1:]
    pattern = pattern.rstrip()
    regex = fnmatch_pathname_to_regex(pattern, directory_only)
    if anchored:
        regex = "".join(["^", regex])
    return IgnoreRule(
        pattern=orig_pattern,
        regex=regex,
        negation=negation,
        directory_only=directory_only,
        anchored=anchored,
        base_path=pathlib.Path(base_path),
        source=source,
    )


# Frustratingly, python's fnmatch doesn't provide the FNM_PATHNAME
# option that .gitignore's behavior depends on.
def fnmatch_pathname_to_regex(pattern: str, directory_only: bool) -> str:
    """
    Implements fnmatch style-behavior, as though with FNM_PATHNAME flagged;
    the path separator will not match shell-style '*' and '.' wildcards.
    """
    i, n = 0, len(pattern)

    seps = [re.escape(os.sep)]
    if os.altsep is not None:
        seps.append(re.escape(os.altsep))
    seps_group = "[" + "|".join(seps) + "]"
    nonsep = r"[^{}]".format("|".join(seps))

    res = []
    while i < n:
        c = pattern[i]
        i += 1
        if c == "*":
            try:
                if pattern[i] == "*":
                    i += 1
                    res.append(".*")
                    if pattern[i] == "/":
                        i += 1
                        res.append("".join([seps_group, "?"]))
                else:
                    res.append("".join([nonsep, "*"]))
            except IndexError:
                res.append("".join([nonsep, "*"]))
        elif c == "?":
            res.append(nonsep)
        elif c == "/":
            res.append(seps_group)
        elif c == "[":
            j = i
            if j < n and pattern[j] == "!":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:
                res.append("\\[")
            else:
                stuff = pattern[i:j].replace("\\", "\\\\")
                i = j + 1
                if stuff[0] == "!":
                    stuff = "".join(["^", stuff[1:]])
                elif stuff[0] == "^":
                    stuff = "".join("\\" + stuff)
                res.append("[{}]".format(stuff))
        else:
            res.append(re.escape(c))
    res.insert(0, "(?ms)")
    if not directory_only:
        res.append("$")
    return "".join(res)


if __name__ == "__main__":
    print(
        b'this is a library only, the executable is named "igittigitt_cli.py"',
        file=sys.stderr,
    )
