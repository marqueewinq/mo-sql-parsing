# More SQL Parsing!

Let's make a SQL parser so we can provide a familiar interface to non-sql datastores!


|Branch      |Status   |
|------------|---------|
|master      | [![Build Status](https://travis-ci.org/klahnakoski/mo-sql-parsing.svg?branch=master)](https://travis-ci.org/klahnakoski/mo-sql-parsing) |
|dev         | [![Build Status](https://travis-ci.org/klahnakoski/mo-sql-parsing.svg?branch=dev)](https://travis-ci.org/klahnakoski/mo-sql-parsing)    |


## Problem Statement

SQL is a familiar language used to access databases. Although, each database vendor has its quirky implementation, there is enough standardization that the average developer does not need to know of those quirks. This familiar core SQL (lowest common denominator, if you will) is useful enough to explore data in primitive ways. It is hoped that, once programmers have reviewed a datastore with basic SQL queries, and they see the value of that data, and they will be motivated to use the datastore's native query format.

## Objectives

The primary objective of this library is to convert SQL queries to JSON-izable parse trees. This originally targeted MySQL, but has grown to include other database vendors. *Please [paste some SQL into a new issue](https://github.com/klahnakoski/mo-sql-parsing/issues) if it does not work for you*

## Project Status

August 2021 -There are [almost 600 tests](https://github.com/klahnakoski/mo-sql-parsing/tree/dev/tests). This parser is good enough for basic usage, including inner queries, `with` clauses, and window functions.  The parser also hanldes Bigquery `create table` statements, but there is still a lot missing to support BigQuery and Redshift queries.  

## Install

    pip install mo-sql-parsing

## Parsing SQL

    >>> from mo_sql_parsing import parse
    >>> import json
    >>> json.dumps(parse("select count(1) from jobs"))
    '{"select": {"value": {"count": 1}}, "from": "jobs"}'
    
Each SQL query is parsed to an object: Each clause is assigned to an object property of the same name. 

    >>> json.dumps(parse("select a as hello, b as world from jobs"))
    '{"select": [{"value": "a", "name": "hello"}, {"value": "b", "name": "world"}], "from": "jobs"}'

The `SELECT` clause is an array of objects containing `name` and `value` properties. 


### SQL Flavours 

There are a few parsing modes you may be interested in:

#### NULL is None

The default output for this parser is to emit a null function `{"null":{}}` wherever `NULL` is encountered in the SQL.  If you would like something different, you can replace nulls with `None` (or anything else for that matter):

    result = parse(sql, null=None)
    
this has been implemented with a post-parse rewriting of the parse tree.

#### MySQL literal strings (broken)

MySQL uses both double quotes and single quotes to declare literal strings.  This is not ansi behaviour.  A specific parse function is provided: 

    result = parse_mysql(sql)


## Generating SQL

You may also generate SQL from the a given JSON document. This is done by the formatter, which is still incomplete (Jan2020).

    >>> from mo_sql_parsing import format
    >>> format({"from":"test", "select":["a.b", "c"]})
    'SELECT a.b, c FROM test'

## Contributing

In the event that the parser is not working for you, you can help make this better but simply pasting your sql (or JSON) into a new issue. Extra points if you describe the problem. Even more points if you submit a PR with a test.  If you also submit a fix, then you also have my gratitude. 


## Run Tests

See [the tests directory](https://github.com/klahnakoski/mo-sql-parsing/tree/dev/tests) for instructions running tests, or writing new ones.

## More about implementation

SQL queries are translated to JSON objects: Each clause is assigned to an object property of the same name.

    
    # SELECT * FROM dual WHERE a>b ORDER BY a+b
    {
        "select": "*", 
        "from": "dual", 
        "where": {"gt": ["a", "b"]}, 
        "orderby": {"value": {"add": ["a", "b"]}}
    }
        
Expressions are also objects, but with only one property: The name of the operation, and the value holding (an array of) parameters for that operation. 

    {op: parameters}

and you can see this pattern in the previous example:

    {"gt": ["a","b"]}
    
## Array Programming

The `mo-sql-parsing.scrub()` method is used liberally throughout the code, and it "simplifies" the JSON.  You may find this form a bit tedious to work with because the JSON property values can be values, lists of values, or missing.  Please consider converting everything to arrays: 


```
def listwrap(value):
    if value is None:
        return []
    elif isinstance(value, list)
        return value
    else:
        return [value]
```  

then you may avoid all the is-it-a-list checks :

```
for select in listwrap(parsed_result.get('select')):
    do_something(select)
```

you may find it easier if all JSON expressions had a list of operands:

```
def normalize(expression):
    if isinstance(expression, dict):
        return [
            {"operator": operator, "operands": [normalize(p) for p in listwrap(operands)]}
            for operator, operands in expression.items()
        ][0]
    return expression
```

[see the smoke test for working example](https://github.com/klahnakoski/mo-sql-parsing/blob/dev/tests/smoke_test.py)
 