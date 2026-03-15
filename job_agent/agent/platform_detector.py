def detect_platform(url):

    url = url.lower()

    if "workday" in url:
        return "workday"

    if "greenhouse" in url:
        return "greenhouse"

    if "lever.co" in url:
        return "lever"

    if "ashbyhq" in url:
        return "ashby"

    if "smartrecruiters" in url:
        return "smartrecruiters"

    if "icims" in url:
        return "icims"

    if "taleo" in url:
        return "taleo"

    if "jobvite" in url:
        return "jobvite"

    if "bamboohr" in url:
        return "bamboo"

    if "successfactors" in url:
        return "successfactors"

    return "generic"