# pytest tests

import pytest
from src.utils.nest_functions import nested_set, add_keys_nested_dict, nested_get
# import asyncio

# Dictionary that is modified / queried as part of tests
input_dict =              { 1: {'name': 'Breaking Bad 1', 'data': {'episodes': 3, 'year': 1991, 'actors': ['Peter', 'Paul', 'Ppacey']}}, 
                            2: {'name': 'Breaking Bad 2', 'data': {'episodes': 6, 'year': 1992, 'actors': ['Weter', 'Waul', 'Wpacey']}},
                            3: {'name': 'Breaking Bad 3', 'data': {'episodes': 9, 'year': 1993, 'actors': ['Zeter', 'Zaul', 'Zpacey']}}}

# @pytest.mark.asyncio
# async def test_nested_set():
@pytest
def test_nested_set():
    expected_output    =  { 1: {'name': 'Breaking Bad 1', 'data': {'episodes': 3, 'year': 1991, 'actors': ['Peter', 'Paul', 'Ppacey']}}, 
                            2: {'name': 'Breaking Bad 2', 'data': {'episodes': 6, 'year': 1994, 'actors': ['Weter', 'Waul', 'Wpacey']}},
                            3: {'name': 'Breaking Bad 3', 'data': {'episodes': 9, 'year': 1993, 'actors': ['Zeter', 'Zaul', 'Zpacey']}}}
    output = input_dict
    # await nested_set(output, [2, 'data' ,'year'], 1994)
    nested_set(output, [2, 'data' ,'year'], 1994)
    assert expected_output == output

@pytest
def test_nested_set_conditions():
    input               = { 1: [{'year': 2001, 'rating': 'high'}, {'year': 2002, 'rating': 'high'}, {'year': 2003, 'rating': 'high'}],
                            2: [{'year': 2001, 'rating': 'high'}, {'year': 2002, 'rating': 'high'}, {'year': 2003, 'rating': 'high'}]}
    expected_output     = { 1: [{'year': 2001, 'rating': 'high'}, {'year': 2002, 'rating': 'high'}, {'year': 2003, 'rating': 'high'}],
                            2: [{'year': 2001, 'rating': 'high'}, {'year': 2002, 'rating': 'high'}, {'year': 2003, 'rating': 'LOW'}]}
    output = input
    nested_set(output, [2, 'rating'], 'LOW', {'year': 2003})
    assert expected_output == output

@pytest
def test_nested_set_conditions_multiple():
    input               = { 1: [{'rating': 'high', 'color': 1, 'stack': 1}, {'rating': 'high', 'color': 2, 'stack': 2}, {'rating': 'high', 'color': 2, 'stack': 1}]}
    expected_output     = { 1: [{'rating': 'high', 'color': 1, 'stack': 1}, {'rating': 'high', 'color': 2, 'stack': 2}, {'rating': 'LOW', 'color': 2, 'stack': 1}]}
    output = input
    nested_set(output, [1, 'rating'], 'LOW', {'color': 2, 'stack': 1})
    assert expected_output == output

@pytest
def test_add_keys_nested_dict():
    expected_output    =  { 1: {'name': 'Breaking Bad 1', 'data': {'episodes': 3, 'year': 1991, 'actors': ['Peter', 'Paul', 'Ppacey']}}, 
                            2: {'name': 'Breaking Bad 2', 'data': {'episodes': 6, 'year': 1994, 'actors': ['Weter', 'Waul', 'Wpacey'], 'spaceship': True}},
                            3: {'name': 'Breaking Bad 3', 'data': {'episodes': 9, 'year': 1993, 'actors': ['Zeter', 'Zaul', 'Zpacey']}}}
    output = input_dict
    add_keys_nested_dict(output, [2, 'data' ,'spaceship'], True)
    assert expected_output == output


@pytest
def test_nested_get():
    input               = { 1: [{'name': 'A', 'color': 1, 'stack': 1}, {'name': 'B', 'color': 2, 'stack': 2}, {'name': 'C', 'color': 2, 'stack': 1}]}
    expected_output     = ['C']
    output =  nested_get(input[1], 'name', {'color': 2, 'stack': 1})
    assert expected_output == output

