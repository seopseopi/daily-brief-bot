"""스포츠 섹션 — KBO(두산) + EPL. 네이버스포츠 비공식 API."""

from datetime import datetime, timedelta

from sources import _market
from sources._shared import KST, fail

DOOSAN_CODE = "OB"
NAVER_SPORTS_GAMES = "https://api-gw.sports.naver.com/schedule/games"
EPL_BIG_CLUBS = {"맨시티", "아스널", "리버풀", "첼시", "맨유", "토트넘"}


def _doosan_line(game):
    is_home = game["homeTeamCode"] == DOOSAN_CODE
    mine = game["homeTeamScore"] if is_home else game["awayTeamScore"]
    theirs = game["awayTeamScore"] if is_home else game["homeTeamScore"]
    opp = game["awayTeamName"] if is_home else game["homeTeamName"]
    outcome = "승" if mine > theirs else "패" if mine < theirs else "무"
    return f"두산 {mine}-{theirs} {opp} ({outcome})"


def _kbo_standings():
    """두산 순위 · 승무패 · 5강 게임차. 네이버스포츠 시즌 통계 API."""
    year = datetime.now(KST).year
    url = f"https://api-gw.sports.naver.com/statistics/categories/kbo/seasons/{year}/teams"
    teams = _market.fetch_json(url)["result"]["seasonTeamStats"]
    by_rank = {t["ranking"]: t for t in teams}
    doosan = next(t for t in teams if t["teamId"] == DOOSAN_CODE)

    record = f"{doosan['winGameCount']}승 {doosan['drawnGameCount']}무 {doosan['loseGameCount']}패"
    rank = doosan["ranking"]
    if rank <= 5:
        sixth = by_rank.get(6)
        cushion = (sixth["gameBehind"] - doosan["gameBehind"]) if sixth else 0
        zone = f"5강권 (6위와 +{cushion:.1f}G)"
    else:
        fifth = by_rank.get(5)
        gap = (doosan["gameBehind"] - fifth["gameBehind"]) if fifth else 0
        zone = f"5강 -{gap:.1f}G"

    return f"{rank}위 ({record}) · {zone}"


def _kbo():
    """두산 최근 경기 결과 + 순위/게임차 + 다음 경기 일정. 네이버스포츠 비공식 API."""
    today = datetime.now(KST).date()
    url = (
        f"{NAVER_SPORTS_GAMES}?fields=basic,score&size=50"
        f"&fromDate={today - timedelta(days=4)}&toDate={today + timedelta(days=1)}"
        "&upperCategoryId=kbaseball&categoryId=kbo"
    )
    games = _market.fetch_json(url)["result"]["games"]
    doosan_games = [g for g in games if DOOSAN_CODE in (g["homeTeamCode"], g["awayTeamCode"])]

    results = sorted((g for g in doosan_games if g["statusCode"] == "RESULT"),
                      key=lambda g: g["gameDate"], reverse=True)
    upcoming = sorted((g for g in doosan_games if g["statusCode"] == "BEFORE"),
                       key=lambda g: g["gameDateTime"])

    if results:
        head = _doosan_line(results[0])
        detail = f"{results[0]['gameDate']} 경기 종료"
    else:
        head, detail = "(최근 경기 결과 없음)", ""

    if upcoming:
        g = upcoming[0]
        is_home = g["homeTeamCode"] == DOOSAN_CODE
        opp = g["awayTeamName"] if is_home else g["homeTeamName"]
        when = datetime.fromisoformat(g["gameDateTime"]).strftime("%m/%d %H:%M")
        next_game = f"다음 경기 {when} vs {opp} ({'홈' if is_home else '원정'})"
    else:
        next_game = "(예정된 경기 없음)"

    try:
        standing = _kbo_standings()
    except Exception as e:
        print(f"[경고] KBO 순위 조회 실패: {type(e).__name__}: {e}")
        fail("두산 순위")
        standing = "(순위 조회 실패)"

    return (head, detail, standing, next_game)


def _epl_highlights(limit=2):
    """빅클럽(맨시티·아스널·리버풀·첼시·맨유·토트넘)이 낀 최근 경기 결과만 추린다."""
    today = datetime.now(KST).date()
    url = (
        f"{NAVER_SPORTS_GAMES}?fields=basic,score&size=50"
        f"&fromDate={today - timedelta(days=5)}&toDate={today}"
        "&upperCategoryId=wfootball&categoryId=epl"
    )
    games = _market.fetch_json(url)["result"]["games"]

    scored = []
    for g in games:
        if g["statusCode"] != "RESULT":
            continue
        big_count = (g["homeTeamName"] in EPL_BIG_CLUBS) + (g["awayTeamName"] in EPL_BIG_CLUBS)
        if big_count:
            scored.append((g["gameDate"], big_count, g))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    lines = [
        f"{g['homeTeamName']} {g['homeTeamScore']}-{g['awayTeamScore']} {g['awayTeamName']}"
        for _, _, g in scored[:limit]
    ]
    return " · ".join(lines) if lines else "(주요 경기 결과 없음)"


def get_sports():
    """KBO(두산) + EPL. 네이버스포츠 비공식 API, 각 종목 독립 fallback."""
    try:
        doosan = _kbo()
    except Exception:
        fail("두산 경기")
        doosan = ("(두산 경기 조회 실패)", "잠시 후 다시 시도해주세요", "", "")

    try:
        football = _epl_highlights()
    except Exception:
        fail("EPL 결과")
        football = "(EPL 결과 조회 실패)"

    return {"doosan": doosan, "football": football}
