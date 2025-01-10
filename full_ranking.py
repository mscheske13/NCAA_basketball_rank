import pandas as pd
from day_trawler import day_scores
from play_by_play import scrape_game
from datetime import timedelta, date, datetime
from get_site import get_site, SLEEP_DELAY
import time
from typing import Tuple, List, Dict


#Constants for start and end of season as defined by NCAA
if date.today().month < 11:
    SEASON_START : date = date(date.today().year - 1, 11, 1)
    SEASON_END : date = date(date.today().year, 4, 8)
else:
    SEASON_START : date = date(date.today().year, 11, 1)
    SEASON_END: date = date(date.today().year + 1, 4, 8)
ROUND_PRECISION = 4

def _average(games: List[float]) -> float:
    total: float = 0
    for game in games:
        total += game
    return round(total / len(games), ROUND_PRECISION)


# Removes all the duplicate games caused by divisional crossover, and removes any games
# not within the range provided
def _filter_games(file : str, start : date, end: date) -> pd.DataFrame:
    games: pd.DataFrame = pd.read_csv(file)
    games.dropna(subset=['Game_id'], inplace=True) # drop games that didn't happen
    games.dropna(subset=['Home_id'], inplace=True) #drop non NCAA opponents
    games.dropna(subset=['Away_id'], inplace=True)
    games.drop_duplicates(subset=['Game_id'], keep=False, inplace=True) #isolates divisions
    games['Date'] = pd.to_datetime(games['Date']).dt.date
    games = games[(games['Date'] >= start) & (games['Date'] <= end)]
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
    games = games[games['Division'] == division]
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

    for _ in range(50):
        for team in league:
            for i in range(len(league[team].opponents)):
                loc_adj : float = 1 # adjust for home field advantage
                if league[team].locs[i] == 'Home':
                    loc_adj = 1.014
                elif league[team].locs[i] == 'Away':
                    loc_adj = .986
                opp: str = league[team].opponents[i]
                j: int = league[opp].ids.index(league[team].ids[i])
                for _ in range(50):
                    league[team].adj_o[i] = league[team].o_ppp[i] / (_average(league[opp].adj_d) * loc_adj)
                    league[team].adj_d[i] = league[team].d_ppp[i] / (_average(league[opp].adj_o) * (2 - loc_adj))
                    league[opp].adj_o[j] = league[opp].o_ppp[j] / (_average(league[team].adj_d) * (2 - loc_adj))
                    league[opp].adj_d[j] = league[opp].d_ppp[j] / (_average(league[team].adj_o) * loc_adj)
    results : pd.DataFrame = pd.DataFrame()
    for i, team in enumerate(league):
        results.at[i, "Team"] = league[team].name
        results.at[i, "ADJO"] = _average(league[team].adj_o)
        results.at[i, "ADJD"] = _average(league[team].adj_d)
        results.at[i, "ADJ_EM"] = round(results.at[i, "ADJO"] - results.at[i, "ADJD"], ROUND_PRECISION)
    return results.sort_values(by='ADJ_EM', ascending=False)



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
    return round(home_ppp, 2), round(away_ppp, ROUND_PRECISION)



# we save all the results to a csv here so if scraping is interrupted
# we can resume where you left off
def _all_games(start : date, end : date, file : str, w : bool = False) -> None:
    sport_code : str = "MBB"
    if w:
        sport_code = "WBB"
    try:
        all_games: pd.DataFrame = pd.read_csv(file)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        all_games: pd.DataFrame = pd.DataFrame()
    index: int = len(all_games)

    while start < end + timedelta(days=1):
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
                all_games.at[index, "Home_ppp"] = round((game["Home_Score"].iloc[-1] / poss), ROUND_PRECISION)
                all_games.at[index, "Away_ppp"] = round((game["Away_Score"].iloc[-1] / poss), ROUND_PRECISION)
                index += 1
                time.sleep(SLEEP_DELAY)
        start += timedelta(days=1)
        time.sleep(SLEEP_DELAY)
        all_games.to_csv(file, index=False)



'''
End user facing function, this returns the actual rankings. 
Arguments taken:
    division: the division you want to rank. Please don't try to make mixed divisional 
    ranking, I can't stop you but it'll be awful without major modifications to ranking logic. 
    If you can get a competent cross divisional ranking, fork the Github and share your code!
    
    Women: A simple bool to rank women's basketball. Will create a new database file for this 
    ranking, if you want to do something crazy like a cross gendered rankings, just merge the files
    
    start/end: A string in the format "mm/dd/yyyy" that gives the start/end inclusive of the 
    ranking range. To simplify ease of use, this program will scrape the entire season up to 
    the current date/season end no matter what. This will take forever, so feel free to change 
    to make it only scrape the ranking range, but do note that progress is saved on your computer
    and I find it's a lot better to just gather all the data needed to rank any arbitrary date range
     
'''
def every_rank(division : int = 1, women : bool = False, start : str = "", end : str = "") -> pd.DataFrame:

    # Sanity check on division
    if not (0 < division < 4):
        print("Error, not a valid division chosen")
        exit(1)

    if not start:
        # default to start of current season
        start_date : date = SEASON_START
    else:
        start_date : date = datetime.strptime(start, "%m/%d/%Y").date()

    if start_date.month < 11:
        year : int = start_date.year - 1
    else:
        year : int = start_date.year


    if not end:
        # default to the end of the season that was started on

        if start_date.month < 11:
            end_date = date(year, 4, 8)
        else:
            end_date = date(year + 1, 4, 8)
    else:
        end_date : date = datetime.strptime(start, "%m/%d/%Y").date()



    if women:
        file = f"games_w_{year}-{year + 1}.csv"
    else:
        file = f"games_m_{year}-{year + 1}.csv"

    try:
        temp_games = pd.read_csv(file)
        scraping_start = datetime.strptime(temp_games['Date'].iloc[-1], "%Y-%m-%d").date()
        scraping_start += timedelta(days=1)
        print(f"Progress file found and resuming where left off. If you wanted to restart the progress"
              f" please delete the contents of {file}, or provide a new file\n")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        print("File empty, creating new dataset using this file...")
        print("Constructing this dataset will take awhile, up to 8 hours depending on season length, and connection speed")
        print("It is likely to fail at some point, but progress willl be saved. Follow the directions given in case of error\n")
        scraping_start = date(year, 11, 1)




    if end_date > date.today():
        end_date = date.today()

    if end_date > SEASON_END:
        end_date = SEASON_END


    # this allows to not need to scrape everything if the user doesn't want to
    # I think it's better to just complete the dataset, but since this won't screw
    # up to the order of games, its fine.
    if scraping_start > end_date:
        print("Dataset already completed for this timespan, running algorithm...\n")
        games: pd.DataFrame = _filter_games(file, start_date, end_date)
        return _rank_them(games, division)

    if scraping_start < start_date:
        print("The provided start date is currently past the planned date to start gathering date.")
        print("Although your ranking will only take into account games on the range provided, the data")
        print("needs to be contiguous to be resusable on new ranges. Thus it will still gather the data")
        print("but it will not be used considered when ranking.")


    try:
        _all_games(scraping_start, end_date, file, women)
    except Exception as e:
        print(e)
        print(f"Connection error at {datetime.now()}, the progress has been saved within {file}")
        print("If you have been given a 'Max tries succeeded' message, give the server at least an hour to recover, or change your wifi.")
        print("Once you restart just use the same arguments, and scraping will begin where you left off\n")
        exit(1)
    print("Dataset completed, running algorithm...")
    games: pd.DataFrame = _filter_games(file, start_date, end_date)
    return _rank_them(games, division)

# sample use
if __name__ == '__main__':
    every_rank(start="11/01/2024", end="4/8/2025", women=False, division=1)





