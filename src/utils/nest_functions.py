
async def nested_set(dic, keys, value, matchConditions=None):
    # Sets the value of a key in a dictionary to a certain value. 
    # If multiple items are present, it can filter for a matching item
    for key in keys[:-1]:
        dic = dic.setdefault(key, {})
    if matchConditions:
        i = 0
        match = False
        for item in dic:   
            for matchCondition in matchConditions:
                if item[matchCondition] != matchConditions[matchCondition]:
                    match = False
                    break
                else:
                    match = True
            if match:
                dic = dic[i]
                break
            i += 1
    dic[keys[-1]] = value


async def add_keys_nested_dict(d, keys, defaultValue = None):
    # Creates a nested value if key does not exist
    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d.setdefault(keys[-1], defaultValue)

async def nested_get(dic, return_attribute, matchConditions):
    # Retrieves a list contained in return_attribute, found within dic based on matchConditions
    i = 0
    match = False
    hits = []
    for item in dic:   
        for matchCondition in matchConditions:
            if item[matchCondition] != matchConditions[matchCondition]:
                match = False
                break
            else:
                match = True
        if match:
            hits.append(dic[i][return_attribute])
        i += 1
    return hits