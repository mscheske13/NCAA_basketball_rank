import io

import pandas as pd
from typing import List, Dict, Tuple
import copy
from get_site import get_site

pd.set_option('display.max_rows', None)


def _score_split(game : pd.DataFrame) -> pd.DataFrame:
    game["Away_Score"] = pd.NA
    game["Home_Score"] = pd.NA
    big_a : int = 0
    big_h : int = 0
    i : int = 0
    for i, score in enumerate(game["Score"]):
        nums : List[int] = score.split("-")
        if i == 0:
            game.at[i, "Away_Score"] = 0
            game.at[i, "Home_Score"] = 0
        elif len(nums) == 1:
            game.at[i, "Away_Score"] = game.at[i - 1, "Away_Score"]
            game.at[i, "Home_Score"] = game.at[i - 1, "Home_Score"]
        else:
            if int(nums[0]) > big_a or int(nums[1]) > big_h:
                big_a = int(nums[0])
                big_h = int(nums[1])
            game.at[i, "Away_Score"] = nums[0]
            game.at[i, "Home_Score"] = nums[1]
    game['Home_Score'] = pd.to_numeric(game['Home_Score'], errors='coerce').astype("Int64")
    game["Away_Score"] = pd.to_numeric(game['Away_Score'], errors='coerce').astype('Int64')
    game.at[i, "Home_Score"] = big_h
    game.at[i, "Away_Score"] = big_a # bandaid fix to a rare phenomenon where the logs
                                     # are wrong and messes up score sorting
    return game



def _time_to_seconds(time_str : str) -> float:
    minutes, seconds, milliseconds = time_str.split(':')
    total_seconds = int(minutes) * 60 + int(seconds) + int(milliseconds) / 100
    return total_seconds


def _game_seconds(game: pd.DataFrame, w : bool = False) -> pd.DataFrame:
    period_length: float = 1200.00
    if w:
        period_length = 480.00
    game["Seconds"] = pd.NA
    for i, time in enumerate(game["Time"]):
        current_time : float = _time_to_seconds(time)
        elapsed : float = period_length - current_time
        #obnoxiously nesting but just adding elapsed time
        # and accounting for arbitrary amount of overtime periods
        if game.at[i, "Period"] > 1 and not w:
            elapsed += 1200
            if game.at[i, "Period"] == 3:
                elapsed += 1200
            for _ in range(game.at[i, "Period"] - 3):
                elapsed += 300
        elif w:
            for n in range(game.at[i, "Period"] - 1):
                if n == 6:
                    break
            for _ in range(game.at[i, "Period"] - 5):
                elapsed += 300
        game.at[i, "Seconds"] = round(elapsed, 2)



    return game


# Shots are tagged with a lot of data, it's better if these are split up
# to bool columns, NA if it's not a shot
def _shot_splitter(game: pd.DataFrame) -> pd.DataFrame:
    # find every shot modifier
    game['Shot_Value'] = pd.NA
    game['Shot_Type'] = pd.NA
    game['Made'] = pd.NA
    game['is_Transition'] = pd.NA
    game['is_Paint'] = pd.NA
    game['2nd_Chance'] = pd.NA
    for i, event in enumerate(game['Event']):
        # split up every non-free throw shot
        if len(event.split('pt')) > 1:
            game.at[i, "Shot_Value"] = int(event.split('pt')[0])
            game.at[i, "Shot_Type"] = event.split()[1]
            if event.split()[-1] == 'made':
                game.at[i, "Made"] = True
            else:
                game.at[i, "Made"] = False
            if 'fastbbreak' in event or 'fromturnover' in event:
                game.at[i, "is_Transition"] = True
            else:
                game.at[i, "is_Transition"] = False
            if 'pointsinthepaint' in event:
                game.at[i, "is_Paint"] = True
            else:
                game.at[i, "is_Paint"] = False
            if '2nd' in event:
                game.at[i, "2nd_Chance"] = True
            else:
                game.at[i, "2nd_Chance"] = False
        else:
            if 'freethrow' in event:
                game.at[i, "Shot_Value"] = 1
                if 'fromturnover' in event:
                    game.at[i, "is_Transition"] = True
                else:
                    game.at[i, "is_Transition"] = False
                if "made" in event:
                    game.at[i, "Made"] = True
                else:
                    game.at[i, "Made"] = False


    return game

#creates a column that tracks which team has possession and another
# to count the total possessions
def _poss_former(game : pd.DataFrame, teams : List[str]) -> pd.DataFrame:
    game["Possession"] = pd.NA
    game["Poss_Count"] = 0
    poss : int = 0
    team : bool = False #indexes teams
    new_half : bool = False # Stops double increments
    for i, player in enumerate(game["Player"][1:]):
        if "-" not in game["Score"][i + 1]:
            game.at[i + 1, "Poss_Count"] = poss
            game.at[i + 1, "Possession"] = teams[team]
            if "end" in game["Score"][i + 1]:
                poss += 1 #for new halves
                new_half = True
            continue #skips all the non-events
        if player == "Team":
            if "defensive" in game["Event"][i + 1]:
                team = not team
                poss += 1
            game.at[i + 1, "Possession"] = teams[team]
            game.at[i + 1, "Poss_Count"] = poss
            continue
        row: List = game.iloc[i + 1].tolist()
        col: int = row.index(player)
        if col < 7:
            team = False
        else:
            team = True
        game.at[i + 1, "Possession"] = teams[team]
        if pd.isna(game["Possession"][i]) or teams[team] != game["Possession"][i]:
            if not new_half:
                poss += 1
        if new_half:
            new_half = False
        game.at[i + 1, "Poss_Count"] = poss


    return game


#The game is more readable if assists, and fouls are counted as
#part of the same event with a secondary player actor
#so this creates that and deletes the old rows
def _event_packer(game : pd.DataFrame) -> pd.DataFrame:
    game["Player_2"] = pd.NA
    game["Event_2"] = pd.NA
    to_delete : List[int] = []
    for i, event in enumerate(game["Event"]):
        if "assist" in event or "foul " in event or "steal" in event\
                or event == " block" or event == " jumpball lost":
            game.at[i + 1, "Player_2"] = game["Player"][i]
            game.at[i + 1, "Event_2"] = event
            to_delete.append(i)
        if event == " foulon": #foulon is poorly named so might as well change it here
            game.at[i, "Event"] = "fouled"

    game.drop(to_delete, inplace=True)
    game.reset_index(drop=True, inplace=True)
    #Do another run through for fouls on shots, needed to pack fouls before this
    #Also fix the player column while we are at it even if its improper
    to_delete: List[int] = []
    for i, event in enumerate(game["Event"]):
        time : str = game["Time"][i]
        if event == "fouled" and time == game["Time"][i + 1] and\
           ("2pt" in game["Event"][i + 1] or "2pt" in game["Event"][i + 1]):

            game.at[i + 1, "Player_2"] = game["Player_2"][i]
            game.at[i + 1, "Event_2"] = game["Event_2"][i]
            to_delete.append(i)
        if event == game["Player"][i]:
            game.at[i, "Player"] = pd.NA
    game.drop(to_delete, inplace=True)
    game.reset_index(drop=True, inplace=True)
    return game

# The events are often out of order, this needs to be fixed to do possession analysis
def _event_sorter(game: pd.DataFrame) -> pd.DataFrame:
    priorities = [
        "game start",
        "period start",
        "jumpball startperiod",
        "jumpball lost",
        "jumpball won",
        "assist",
        "jumpball",
        "steal",
        "turnover ",
        "foul ",
        "foulon",
        "block",
        "tipin",
        "2pt",
        "3pt",
        "1of2",
        "1of3",
        "rebound",
        "2of3",
        "1of1",
        "2of2",
        "3of3",
        "timeout",
        "end"
    ]
    new_order : List[int] = []

    # Find all events that happen at the same time and sort them according
    # to priorites. Then add the indices to the new order and rearrange the df
    # accordingly
    for i, time in enumerate(game["Time"]):
        if i < len(new_order): #compensate for moving ahead in for loop
            continue
        same_times: List[int] = [i]
        index: int = i + 1
        for subsequent in game["Time"][i + 1:]:
            if time != subsequent:
                break
            same_times.append(index)
            index += 1
        if len(same_times) == 1:
            new_order.append(same_times[0])
            continue
        tup_list: List[Tuple[int, int]] = []
        # creates tups of the priority order, and index, then sorts by order
        # adds the indices to the new_order list
        for spot in same_times:
            event : str = game["Event"][spot]
            for j, priority in enumerate(priorities):
                if event == " block": #due to how they write out the event we need to make an exception here
                    tup: Tuple[int, int] = (0, spot)
                    tup_list.append(tup)
                    break
                if priority in event:
                    # this looks really stupid but trust me the reason
                    # it exists is even more stupid than this
                    if j == 12:
                        j = 18
                    tup : Tuple [int, int] = (j, spot)
                    tup_list.append(tup)
                    break
        tup_list.sort()
        for tupl in tup_list:
            new_order.append(tupl[1])

    game = game.iloc[new_order]
    game.reset_index(drop=True, inplace=True)
    return game



def _get_starters(df : pd.DataFrame) -> List [List[str]]:
    starters : List [List[str]] = [[], []]
    not_starters : List[str] = []
    for index, n in enumerate([1, 3]):
        for event in df[df.columns[n]]:
            if pd.isna(event):
               continue
            split_up : List[str] = event.split(',') # splits to [player, happening]
            player : str = split_up[0]
            if len(split_up) == 1 or player == "Team":
                continue
            if " in" in split_up[1]:
                not_starters.append(player)
                continue # Skips players who subbed in
            if player not in not_starters and player not in starters[index]:
                starters[index].append(player)
            if len(starters[index]) == 5:
                break
    return starters

# Helper Function for sorting players based on position
def _get_positions(game_id : int) -> Dict[str, str]:
    url: str = f"https://stats.ncaa.org/contests/{game_id}/individual_stats"
    dataframes: List[pd.DataFrame] = pd.read_html(get_site(url))
    positions : Dict[str, str] = {}
    positions.update(dataframes[3].set_index('Name')['P'].to_dict())
    positions.update(dataframes[4].set_index('Name')['P'].to_dict())
    return positions

# Uses Dutch flag algorithm to put centers on end, guards in front.
# Only positions on site are Center, Guard, Forward
def _order_players(on_court  : List[str],
                   positions :Dict[str, str]) -> None:

    on_court.sort() #sort the list alphabetically first to get consistent sorts
    low : int = 0
    i : int = 0
    high : int = 4
    while i <= high:
        position = positions.get(on_court[i])
        # very rarely a pbp and team_data is not congruent
        # so we default to guard in this case. See Joel Ofori of new Middlebury
        if not position:
            position = "G"

        if position == "G":
            on_court[i], on_court[low] = on_court[low], on_court[i]
            low += 1
        elif position == "C":
            on_court[i], on_court[high] = on_court[high], on_court[i]
            high -= 1
        i += 1

    return


def _build_lineups(game_id : int, game : pd.DataFrame) -> pd.DataFrame:
    positions : Dict[str, str] = _get_positions(game_id)
    starters : List[List[str]]= _get_starters(game)
    away_lineups : List[List[str]] = []
    home_lineups : List[List[str]] = []
    prev : List[str] = starters[0] # whenever the lineup isn't full we add the last instance when it was
    rows_to_drop : List[int] = [] # Since we'll have lineups at all times, we can drop events with subs to make it easier to read
    for i, event in enumerate(game[game.columns[1]]):
        if pd.isna(event):
            if len(starters[0]) == 5: #reduancy because orders get screwed up on webpage
                away_lineups.append(copy.deepcopy(starters[0]))
            else:
                away_lineups.append(copy.deepcopy(prev))
            continue
        player : str = event.split(",")[0]
        if "substitution out" in event:
            try:
                starters[0].remove(player)
            except ValueError:
                print("Incomplete substitution data, using estimate")
            rows_to_drop.append(i)
        elif "substitution in" in event:
            starters[0].append(player)
            rows_to_drop.append(i)
        if len(starters[0]) == 5:
            _order_players(starters[0], positions)
            away_lineups.append(copy.deepcopy(starters[0]))
            prev = copy.deepcopy(starters[0])
        elif len(starters[0]) != 5:
            away_lineups.append(copy.deepcopy(prev))

    prev = starters[1]
    for i, event in enumerate(game[game.columns[3]]):
        if pd.isna(event):
            if len(starters[1]) == 5:
                home_lineups.append(copy.deepcopy(starters[1]))
            else:
                home_lineups.append(copy.deepcopy(prev))
            continue
        player: str = event.split(",")[0]
        if "substitution out" in event:
            try:
                starters[1].remove(player)
            except ValueError:
                print("Incomplete substitution data, using estimate")
            rows_to_drop.append(i)
        elif "substitution in" in event:
            starters[1].append(player)
            rows_to_drop.append(i)
        if len(starters[1]) == 5:
            _order_players(starters[1], positions)
            home_lineups.append(copy.deepcopy(starters[1]))
            prev = copy.deepcopy(starters[1])
        elif len(starters[1]) != 5:
            home_lineups.append(copy.deepcopy(prev))

    away_lineup_df = pd.DataFrame(away_lineups, columns=["Away_1",
                                                         "Away_2",
                                                         "Away_3",
                                                         "Away_4",
                                                         "Away_5"])
    home_lineup_df = pd.DataFrame(home_lineups, columns=["Home_1",
                                                         "Home_2",
                                                          "Home_3",
                                                          "Home_4",
                                                          "Home_5"])

    game = pd.concat([game, away_lineup_df, home_lineup_df], axis=1)
    game.drop(rows_to_drop, inplace=True)
    game.reset_index(drop=True, inplace=True)
    # Combine the 2 team streams into one, then split by player and Event delete old streams
    game['Event'] = game[game.columns[1]].combine_first(game[game.columns[3]])
    game[['Player', 'Event']] = game['Event'].str.rsplit(',',  n=1,  expand=True)
    game['Event'] = game['Event'].fillna(game['Player'])
    game.drop(columns=[game.columns[1], game.columns[3]], inplace=True)
    return game


# sometimes the scores columns get reversed for some reason, easy fix
# just use the score table
def _fix_glitch(table : pd.DataFrame, game : pd.DataFrame) -> pd.DataFrame:
    if int(table[list(table.columns)[-1]][1]) != game["Away_Score"].iloc[-1]:
        print("Error detected in scores column, flipping cols")
        game['Away_Score'], game['Home_Score'] = game['Home_Score'], game['Away_Score']
    return game


# very simple garbage time definition, assumes a team gets
# one possession a minute. If a lead is greater than 10, under 10 minutes left
# and possessions left * 3 < lead than it is considered garbage time
def _is_garbage(game: pd.DataFrame) -> pd.DataFrame:
    game["is_Garbage_Time"] = False
    # if a game is overtime, there's no garbage time
    if game["Seconds"].iloc[-1] > 2401:
        return game
    for i,  secs in enumerate(game['Seconds']):
        if secs < 1800:
            continue
        lead : int = abs(game["Away_Score"][i] - game["Home_Score"][i])
        # to prevent it from constantly switching back at the edge
        # the lead needs to be below 10 is we are going to unswitch the
        # measure
        if lead > 10 and game["is_Garbage_Time"][i - 1]:
            game.at[i, "is_Garbage_Time"] = True
        elif lead > 15 and lead > (((2400 - secs) // 20) + 1):
            game.at[i, "is_Garbage_Time"] = True
    return game

def scrape_game(game_id : int) -> pd.DataFrame:
    url : str = f"https://stats.ncaa.org/contests/{game_id}/play_by_play"
    site_content : io.StringIO = get_site(url)
    dataframes: List[pd.DataFrame] = pd.read_html(site_content)

    # Add a halves column here because it's easier, even if it is improper
    for i, df in enumerate(dataframes[3:]):
        df["Period"] = i + 1
    game : pd.DataFrame = pd.concat(dataframes[3:], axis=0, ignore_index=True)
    if "-" in game["Score"][0]:
        print("Play by play logged under old format, no support for now", game_id)
        return pd.DataFrame()
    teams : List[str] = [game.columns[1], game.columns[3]] # team names
    # sometimes the pbp data is null save for announcements of each period.
    # 20 is arbitrary but will save us up to 18 OTs or 16 in women's so it should
    # be fine
    if len(game) < 20:
        print("Play by play not logged, consider scraping box score")
        return pd.DataFrame()
    game.reset_index(drop=True, inplace=True)
    game = _build_lineups(game_id, game)
    game = _score_split(game)
    game = _event_sorter(game)
    game = _event_packer(game)
    game = _poss_former(game, teams)
    game = _shot_splitter(game)
    game = _game_seconds(game)
    game = _score_split(game)
    game.drop("Score", axis=1, inplace=True)
    game["Id"] = game_id
    game = _fix_glitch(dataframes[1], game)
    game = _is_garbage(game)

    desired_order : List[str] = [
        "Period", "Time", "Seconds", "Away_Score", "Home_Score", "Event",
        "Player", "Player_2", "Event_2", "Possession", "Poss_Count",
        "Shot_Value", "Shot_Type", "Made", "is_Transition", "is_Paint",
        "2nd_Chance", "is_Garbage_Time", "Away_1", "Away_2", "Away_3", "Away_4", "Away_5",
        "Home_1", "Home_2", "Home_3", "Home_4", "Home_5", "Id"
    ]

    # Rearrange columns
    game = game[desired_order]
    return game





