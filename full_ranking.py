import sys
import pandas as pd
from day_trawler import day_scores
from play_by_play import scrape_game
from datetime import datetime, timedelta
from get_site import get_site, SLEEP_DELAY
import time
from typing import Tuple, List, Dict




def _average(games: List[float]) -> float:
    total: float = 0
    for game in games:
        total += game
    return round(total / len(games), 4)


def _isolate_divisions(file : str) -> pd.DataFrame:
    games: pd.DataFrame = pd.read_csv(file)
    games.dropna(subset=['Game_id'], inplace=True) # drop games that didn't happen
    games.dropna(subset=['Home_id'], inplace=True) #drop non NCAA opponents
    games.dropna(subset=['Away_id'], inplace=True)
    games.drop_duplicates(subset=['Game_id'], keep=False, inplace=True) #isolates divisions
    return games


class Team:
    def __init__(self, name):
        self.name = name
        self.opponents = []
        self.o_ppp = []
        self.d_ppp = []
        self.adj_o = []
        self.adj_d = []
        self.locs = []
        self.ids = []

def _rank_them(games: pd.DataFrame, division : int) -> pd.DataFrame:
    league : Dict[str, Team] = {}
    games = games[games['Division'] == 1]
    for index, row in games.iterrows():
        away : str = row["Away_Team"]
        home : str = row["Home_Team"]
        if away not in league:
            league[away] = Team(away)
        if home not in league:
            league[home] = Team(home)
        league[home].o_ppp.append(row["Home_ppp"])
        league[home].d_ppp.append(row["Away_ppp"])
        league[home].adj_o.append(row["Home_ppp"])
        league[home].adj_d.append(row["Away_ppp"])
        league[home].opponents.append(row["Away_Team"])
        league[home].ids.append(row["Game_id"])
        league[away].d_ppp.append(row["Home_ppp"])
        league[away].o_ppp.append(row["Away_ppp"])
        league[away].opponents.append(row["Home_Team"])
        league[away].adj_d.append(row["Home_ppp"])
        league[away].adj_o.append(row["Away_ppp"])
        league[away].ids.append(row["Game_id"])
        if row["Home_Team"] == row["Location"]:
            league[home].locs.append("Home")
            league[away].locs.append("Away")
        else:
            league[home].locs.append("Neutral")
            league[away].locs.append("Neutral")

    for _ in range(10):
        for team in league:
            for i in range(len(league[team].opponents)):
                loc_adj : float = 1 # adjust for home field advantage
                if league[team].locs[i] == 'Home':
                    loc_adj = 1.014
                elif league[team].locs[i] == 'Away':
                    loc_adj = .986
                opp: str = league[team].opponents[i]
                j: int = league[opp].ids.index(league[team].ids[i])
                for _ in range(10):
                    league[team].adj_o[i] = league[team].o_ppp[i] / (_average(league[opp].adj_d) * loc_adj)
                    league[team].adj_d[i] = league[team].d_ppp[i] / (_average(league[opp].adj_o) * (2 - loc_adj))
                    league[opp].adj_o[j] = league[opp].o_ppp[j] / (_average(league[team].adj_d) * (2 - loc_adj))
                    league[opp].adj_d[j] = league[opp].d_ppp[j] / (_average(league[team].adj_o) * loc_adj)
    results : pd.DataFrame = pd.DataFrame()
    for i, team in enumerate(league):
        results.at[i, "Team"] = league[team].name
        results.at[i, "ADJO"] = _average(league[team].adj_o)
        results.at[i, "ADJD"] = _average(league[team].adj_d)
        results.at[i, "ADJ_EM"] = _average(league[team].adj_o) - _average(league[team].adj_d)
    return results



def _ppp_est(game_id: int) -> Tuple[float, float]:
    url: str = f"https://stats.ncaa.org/contests/{game_id}/team_stats"
    stats: pd.DataFrame = pd.read_html(get_site(url))[3]
    home: str = list(stats.columns)[2]
    away: str = list(stats.columns)[1]
    col = list(stats.columns)[0]
    fgah = fgaa = orebsh = orebsa = toah = toa = ftah = ftaa = ptsh = ptsa = 0
    for i, stat in enumerate(stats[col]):
        if stat == "FGA":
            fgah: int = int(stats.at[i, home])
            fgaa: int = int(stats.at[i, away])
        elif stat == "ORebs":
            orebsh: int = int(stats.at[i, home])
            orebsa: int = int(stats.at[i, away])
        elif stat == "TO":
            toah: int = int(stats.at[i, home])
            toa: int = int(stats.at[i, away])
        elif stat == "FTA":
            ftah = int(stats.at[i, home])
            ftaa: int = int(stats.at[i, away])
        elif stat == "PTS":
            ptsh = int(stats.at[i, home])
            ptsa = int(stats.at[i, away])

    home_ppp = ((fgah - orebsh) + toah + (ftah * .44)) / ptsh
    away_ppp = ((fgaa - orebsa) + toa + (ftaa * .44)) / ptsa
    return round(home_ppp, 2), round(away_ppp, 2)


def _trawl_games() -> None:
    everything : pd.DataFrame = pd.DataFrame()
    for n in [1, 2, 3]:
        print(f"Starting division {n}")
        date: datetime = datetime(2024, 11, 1)
        while True:
            if date.month == 12 and date.day == 2:
                break
            print(date)
            day: pd.DataFrame = day_scores(date, "MBB", division=n)
            everything = pd.concat([everything, day], ignore_index=True)
            date += timedelta(days=1)
            time.sleep(SLEEP_DELAY)
    everything.to_csv("scores.csv")


# we save all the results to a csv here so if scraping is interrupted
# we can resume where you left off
def _all_games(start : datetime, end : datetime, file : str, w : bool = False) -> None:
    sport_code : str = "MBB"
    if w:
        sport_code = "WBB"
    try:
        all_games: pd.DataFrame = pd.read_csv(file)
    except FileNotFoundError:
        all_games: pd.DataFrame = pd.DataFrame()
    index: int = len(all_games)
    today = datetime.today()
    today.replace(hour=0, second=0, microsecond=0)
    if end > today:
        end = today
    while start < end:
        print(start)
        for n in [1, 2, 3]:
            day: pd.DataFrame = day_scores(start, sport_code, division=n)
            if day.empty:
                time.sleep(SLEEP_DELAY)
                continue
            all_games = pd.concat([all_games, day], ignore_index=True)
            for i, game_id in enumerate(day["Game_id"]):
                if pd.isna(game_id):
                    index += 1
                    continue
                all_games.at[index, "Home_Team"] = day["Home_Team"][i]
                all_games.at[index, "Away_Team"] = day["Away_Team"][i]
                try:
                    game: pd.DataFrame = scrape_game(game_id)
                except ValueError:
                    print(game_id, "not available")
                    index += 1
                    continue

                if game.empty:
                    time.sleep(SLEEP_DELAY)
                    print(f"Retrieving {game_id} play by play failed. Using box score estimate")
                    ppps: Tuple[float, float] = _ppp_est(game_id)
                    all_games.at[index, "Home_ppp"] = ppps[0]
                    all_games.at[index, "Away_ppp"] = ppps[1]
                    all_games.at[index, "Division"] = n
                    index += 1
                    time.sleep(SLEEP_DELAY)
                    continue
                if game["is_Garbage_Time"].any():
                    cutoff_index = game[game["is_Garbage_Time"] == True].index[0]
                    game = game.loc[:cutoff_index]
                poss: int = game["Poss_Count"].iloc[-1] // 2
                all_games.at[index, "Home_ppp"] = round((game["Home_Score"].iloc[-1] / poss), 2)
                all_games.at[index, "Away_ppp"] = round((game["Away_Score"].iloc[-1] / poss), 2)
                all_games.at[index, "Division"] = n
                index += 1
                time.sleep(SLEEP_DELAY)
        start += timedelta(days=1)
        time.sleep(SLEEP_DELAY)
        all_games.to_csv(file, index=False)


def every_rank(start : datetime, end : datetime, file : str, division : int, w : bool = False) -> pd.DataFrame:
    try:
        _all_games(start, end, file, w)
    except:
        print(f"connection error, the progress has been saved within {file}, to resume, try again with the start date most recently printed")
        sys.exit(1)
    games: pd.DataFrame = _isolate_divisions(file)
    return _rank_them(games, division)





