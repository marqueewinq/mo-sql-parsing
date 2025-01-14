# encoding: utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Contact: Kyle Lahnakoski (kyle@lahnakoski.com)
#

from __future__ import absolute_import, division, unicode_literals

import ast

from mo_dots import is_data, is_null
from mo_future import text, number_types, binary_type

from mo_parsing import *
from mo_parsing.utils import is_number, listwrap, alphanums

IDENT_CHAR = alphanums + "@_$"
SQL_NULL = {"null": {}}

null_locations = []


def scrub(result):
    if result is SQL_NULL:
        return SQL_NULL
    elif result == None:
        return None
    elif isinstance(result, text):
        return result
    elif isinstance(result, binary_type):
        return result.decode("utf8")
    elif isinstance(result, number_types):
        return result
    elif isinstance(result, dict) and not result:
        return result
    elif isinstance(result, list):
        output = [rr for r in result for rr in [scrub(r)]]

        if not output:
            return None
        elif len(output) == 1:
            return output[0]
        else:
            for i, v in enumerate(output):
                if v is SQL_NULL:
                    null_locations.append((output, i))
            return output
    else:
        # ATTEMPT A DICT INTERPRETATION
        try:
            kv_pairs = list(result.items())
        except Exception as c:
            print(c)
        output = {k: vv for k, v in kv_pairs for vv in [scrub(v)] if not is_null(vv)}
        if isinstance(result, dict) or output:
            for k, v in output.items():
                if v is SQL_NULL:
                    null_locations.append((output, k))
            return output
        return scrub(list(result))


def scrub_literal(candidate):
    # IF ALL MEMBERS OF A LIST ARE LITERALS, THEN MAKE THE LIST LITERAL
    if all(isinstance(r, number_types) for r in candidate):
        pass
    elif all(
        isinstance(r, number_types) or (is_data(r) and "literal" in r.keys())
        for r in candidate
    ):
        candidate = {"literal": [r["literal"] if is_data(r) else r for r in candidate]}
    return candidate


def _chunk(values, size):
    acc = []
    for v in values:
        acc.append(v)
        if len(acc) == size:
            yield acc
            acc = []
    if acc:
        yield acc


def to_json_operator(tokens):
    # ARRANGE INTO {op: params} FORMAT
    length = len(tokens.tokens)
    if length == 2:
        # UNARY OPERATOR
        op = tokens.tokens[0].type.parser_name
        if op == "neg" and is_number(tokens[1]):
            return -tokens[1]
        return {op: tokens[1]}
    elif length == 5:
        # TRINARY OPERATOR
        return {tokens.tokens[1].type.parser_name: [tokens[0], tokens[2], tokens[4]]}

    op = tokens[1]
    if not isinstance(op, text):
        op = op.type.parser_name
    op = binary_ops.get(op, op)
    if op == "eq":
        if tokens[2] is SQL_NULL:
            return {"missing": tokens[0]}
        elif tokens[0] is SQL_NULL:
            return {"missing": tokens[2]}
    elif op == "neq":
        if tokens[2] is SQL_NULL:
            return {"exists": tokens[0]}
        elif tokens[0] is SQL_NULL:
            return {"exists": tokens[2]}
    elif op == "is":
        if tokens[2] is SQL_NULL:
            return {"missing": tokens[0]}
        else:
            return {"exists": tokens[0]}
    elif op == "is_not":
        if tokens[2] is SQL_NULL:
            return {"exists": tokens[0]}
        else:
            return {"missing": tokens[0]}

    operands = [tokens[0], tokens[2]]
    binary_op = {op: operands}

    if op in {"add", "mul", "and", "or"}:
        # ASSOCIATIVE OPERATORS
        acc = []
        for operand in operands:
            while isinstance(operand, ParseResults) and isinstance(operand.type, Group):
                # PARENTHESES CAUSE EXTRA GROUP LAYERS
                operand = operand[0]

            if isinstance(operand, list):
                acc.append(operand)
            elif isinstance(operand, dict) and operand.get(op):
                acc.extend(operand.get(op))
            else:
                acc.append(operand)
        binary_op = {op: acc}
    return binary_op


def to_tuple_call(tokens):
    # IS THIS ONE VALUE IN (), OR MANY?
    tokens = list(tokens)
    if len(tokens) == 1:
        return [tokens[0]]
    return [scrub_literal(tokens)]


binary_ops = {
    "::": "cast",
    "COLLATE": "collate",
    "||": "concat",
    "*": "mul",
    "/": "div",
    "%": "mod",
    "+": "add",
    "-": "sub",
    "&": "binary_and",
    "|": "binary_or",
    "<": "lt",
    "<=": "lte",
    ">": "gt",
    ">=": "gte",
    "=": "eq",
    "==": "eq",
    "<=>": "eq!",  # https://sparkbyexamples.com/apache-hive/hive-relational-arithmetic-logical-operators/
    "!=": "neq",
    "<>": "neq",
    "not in": "nin",
    "is not": "neq",
    "is": "eq",
    "similar to": "similar_to",
    "not like": "not_like",
    "not rlike": "not_rlike",
    "not simlilar to": "not_similar_to",
    "or": "or",
    "and": "and",
}


def to_trim_call(tokens):
    frum = tokens['from']
    if not frum:
        return {"trim": tokens["chars"]}
    return {"trim": frum, "characters": tokens['chars']}


def to_json_call(tokens):
    # ARRANGE INTO {op: params} FORMAT
    op = tokens["op"].lower()
    op = binary_ops.get(op, op)

    params = tokens["params"]
    if not params:
        params = {}
    if tokens["ignore_nulls"]:
        ignore_nulls = True
    else:
        ignore_nulls = None

    return ParseResults(
        tokens.type,
        tokens.start,
        tokens.end,
        [{op: params, "ignore_nulls": ignore_nulls}],
    )


def to_interval_call(tokens):
    # ARRANGE INTO {interval: [amount, type]} FORMAT
    params = tokens["params"]
    if not params:
        params = {}
    if params.length() == 2:
        return {"interval": params}

    return {"add": [{"interval": p} for p in _chunk(params, size=2)]}


def to_case_call(tokens):
    cases = list(tokens["case"])
    elze = tokens["else"]
    if elze != None:
        cases.append(elze)
    return {"case": cases}


def to_switch_call(tokens):
    # CONVERT TO CLASSIC CASE STATEMENT
    value = tokens["value"]
    cases = list(tokens["case"])
    for c in cases:
        c["when"] = {"eq": [value, c["when"]]}
    elze = tokens["else"]
    if elze != None:
        cases.append(elze)
    return {"case": cases}


def to_when_call(tokens):
    tok = tokens
    return {"when": tok["when"], "then": tok["then"]}


def to_join_call(tokens):
    op = " ".join(tokens["op"])
    if tokens["join"]["name"]:
        output = {op: {
            "name": tokens["join"]["name"],
            "value": tokens["join"]["value"],
        }}
    else:
        output = {op: tokens["join"]}

    output["on"] = tokens["on"]
    output["using"] = tokens["using"]
    return output


def to_expression_call(tokens):
    over = tokens["over"]
    within = tokens["within"]
    if over or within:
        return

    expr = ParseResults(
        tokens.type, tokens.start, tokens.end, listwrap(tokens["value"])
    )
    return expr


def to_alias(tokens):
    cols = tokens["col"]
    name = tokens[0][0]
    if cols:
        return {name: cols}
    return name


def to_top_clause(tokens):
    value = tokens["value"]
    if not value:
        return None
    elif tokens["ties"]:
        output = {}
        output["ties"] = True
        if tokens["percent"]:
            output["percent"] = value
        else:
            output["value"] = value
        return output
    elif tokens["percent"]:
        return {"percent": value}
    else:
        return [value]


def to_select_call(tokens):
    value = tokens["value"]
    if value.value() == "*":
        return ["*"]

    if value["over"] or value["within"]:
        output = ParseResults(tokens.type, tokens.start, tokens.end, value.tokens)
        output["name"] = tokens["name"]
        return output
    else:
        return


def to_union_call(tokens):
    unions = tokens["union"]
    if unions.type.parser_name == "unordered sql":
        output = {k: v for k, v in unions.items()}  # REMOVE THE Group()
    else:
        unions = list(unions)
        sources = [unions[i] for i in range(0, len(unions), 2)]
        operators = ["_".join(unions[i]) for i in range(1, len(unions), 2)]
        acc = sources[-1]
        last_union = None
        for op, so in reversed(list(zip(operators, sources))):
            if op == last_union:
                acc[op] = [so] + acc[op]
            else:
                acc = {op: [so, acc]}
            last_union = op

        if not tokens["orderby"] and not tokens["offset"] and not tokens["limit"]:
            return acc
        else:
            output = {"from": acc}

    output["orderby"] = tokens["orderby"]
    output["offset"] = tokens["offset"]
    output["limit"] = tokens["limit"]
    return output


def to_statement(tokens):
    output = tokens["query"][0]
    output["with"] = tokens["with"]
    return output


def unquote(tokens):
    val = tokens[0]
    if val.startswith("'") and val.endswith("'"):
        val = "'" + val[1:-1].replace("''", "\\'") + "'"
    elif val.startswith('"') and val.endswith('"'):
        val = '"' + val[1:-1].replace('""', '\\"') + '"'
    elif val.startswith("`") and val.endswith("`"):
        val = '"' + val[1:-1].replace("``", "`").replace('"', '\\"') + '"'
    elif val.startswith("[") and val.endswith("]"):
        val = '"' + val[1:-1].replace("]]", "]").replace('"', '\\"') + '"'
    elif val.startswith("+"):
        val = val[1:]
    un = ast.literal_eval(val).replace(".", "\\.")
    return un


def to_string(tokens):
    val = tokens[0]
    val = "'" + val[1:-1].replace("''", "\\'") + "'"
    return {"literal": ast.literal_eval(val)}


# NUMBERS
realNum = (
    Regex(r"[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?")
    .set_parser_name("float")
    .addParseAction(lambda t: float(t[0]))
)


def parse_int(tokens):
    if "e" in tokens[0].lower():
        return int(float(tokens[0]))
    else:
        return int(tokens[0])


intNum = (
    Regex(r"[+-]?\d+([eE]\+?\d+)?").set_parser_name("int").addParseAction(parse_int)
)
hexNum = (
    Regex(r"0x[0-9a-fA-F]+")
    .set_parser_name("hex")
    .addParseAction(lambda t: {"hex": t[0][2:]})
)

# STRINGS
ansi_string = Regex(r"\'(\'\'|[^'])*\'").addParseAction(to_string)
mysql_doublequote_string = Regex(r'\"(\"\"|[^"])*\"').addParseAction(to_string)

# BASIC IDENTIFIERS
ansi_ident = Regex(r'\"(\"\"|[^"])*\"').addParseAction(unquote)
mysql_backtick_ident = Regex(r"\`(\`\`|[^`])*\`").addParseAction(unquote)
sqlserver_ident = Regex(r"\[(\]\]|[^\]])*\]").addParseAction(unquote)

expr = Forward()
