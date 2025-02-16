def nested_set(dic, keys, value, matchConditions=None):
    # Sets the value of a key in a dictionary to a certain value.
    # If multiple items are present, it can filter for a matching item
    for key in keys[:-1]:
        dic = dic.setdefault(key, {})

    if matchConditions:
        for i, item in enumerate(dic):
            if all(item.get(cond) == matchConditions[cond] for cond in matchConditions):
                dic = dic[i]
                break

    dic[keys[-1]] = value


def add_keys_nested_dict(d, keys, defaultValue=None):
    # Creates a nested value if key does not exist
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d.setdefault(keys[-1], defaultValue)


def nested_get(dic, return_attribute, matchConditions):
    # Retrieves a list contained in return_attribute, found within dic based on matchConditions
    return [item[return_attribute] for item in dic if all(item.get(cond) == matchConditions[cond] for cond in matchConditions)]