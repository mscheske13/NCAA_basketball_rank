from bs4 import BeautifulSoup as Soup
from typing import List, Tuple
import pandas as pd
from datetime import datetime, timedelta
import time
from get_site import get_site






def _event_location(info : str) -> Tuple[str, any]:
    location = pd.NA
    event : str = "Regular Season"
    split : List[str] = info.split(',')
    if info[0] == '@':
        location = split[0]
        location += (',' + split[1].split('(')[0])
        location = location[1:]
    if len(split) == 2:
        if len(split[1].split('(')) == 2:
            event = split[1].split('(')[1][:-1]
    return event, location


def _wins_and_losses(team : str) -> Tuple[str, str]:
    ex : Tuple [str, str]
    separated_record : List[str] = team.split("(")[-1].split('-')
    if len(separated_record) == 1:
        return '0', '0'
    wins = separated_record[0]
    losses : str = separated_record[1][:-1]
    return wins, losses

def _set_url(date: datetime, sport_code : str, division : int) -> str:
    year : int = date.year
    if date.month > 7:
        year += 1 #Games in november december are considered part of next season
    str_date : str = date.strftime("%m/%d/%Y").replace("/", "%2F")
    url: str = (f"https://stats.ncaa.org/contests/livestream_scoreboards?utf8"
                f"=%E2%9C%93&sport_code={sport_code}&academic_year={year}&division={division}&game"
                f"_date={str_date}&commit=Submit")
    return url


# Separating this out because it's not all the same job anymore
def _cleanup(scores : pd.DataFrame) -> pd.DataFrame:
    # deal with thousands commas
    scores['Attendance'] = scores['Attendance'].str.replace(',', '').astype(int)
    scores['Home_Seed'] = pd.to_numeric(scores['Home_Seed'], errors='coerce').astype("Int64")
    scores["Away_Seed"] = pd.to_numeric(scores['Away_Seed'], errors='coerce').astype('Int64')
    scores["Home_Wins"] = pd.to_numeric(scores['Home_Wins'], errors='coerce').astype("Int64")
    scores["Home_Losses"] = pd.to_numeric(scores['Home_Losses'], errors='coerce').astype("Int64")
    scores["Away_Losses"] = pd.to_numeric(scores['Away_Losses'], errors='coerce').astype("Int64")
    scores["Away_Wins"] = pd.to_numeric(scores['Away_Wins'], errors='coerce').astype("Int64")
    scores['Home_Score'] = pd.to_numeric(scores['Home_Score'], errors='coerce').astype("Int64")
    scores["Away_Score"] = pd.to_numeric(scores['Away_Score'], errors='coerce').astype('Int64')
    scores["Away_id"] = pd.to_numeric(scores['Away_id'], errors='coerce').astype('Int64')
    scores["Home_id"] = pd.to_numeric(scores['Home_id'], errors='coerce').astype('Int64')
    scores["Game_id"] = pd.to_numeric(scores['Game_id'], errors='coerce').astype('Int64')

    desired_order = [
        'Date', 'Time', 'Event', 'Location', 'Away_Seed', 'Away_Team',
        'Away_Score','Home_Seed', 'Home_Team', 'Home_Score', 'Away_Wins',
        'Away_Losses', 'Home_Wins', 'Home_Losses', 'Away_id', 'Home_id',
        'Game_id']
    scores = scores[desired_order]
    scores.reset_index(drop=True, inplace=True)
    return scores

#  universal for all sports
# obnoxiously long and confusing function but just html and string manips
def day_scores(date: datetime, sport_code : str, division : int = 1) -> pd.DataFrame:

    soup : Soup = Soup(get_site(_set_url(date, sport_code, division)), 'html.parser')
    box_scores : List[Soup] = soup.find_all('table')
    scores : pd.DataFrame = pd.DataFrame()
    # need to construct a dataframe from scratch so just initialize everything
    # technically unnecessary but makes a little bit clearer to read with default init
    scores["Time"] = pd.NA
    scores["Attendance"] = pd.NA
    scores["Event"] = pd.NA
    scores["Location"] = pd.NA
    scores["Home_Seed"] = pd.NA
    scores["Away_Seed"] = pd.NA
    scores["Home_Wins"] = pd.NA
    scores["Home_Losses"] = pd.NA
    scores["Away_Losses"] = pd.NA
    scores["Away_Wins"] = pd.NA
    scores["Away_id"] = pd.NA
    scores["Home_id"] = pd.NA
    scores["Game_id"] = pd.NA
    scores["Ongoing"] = pd.NA
    if len(box_scores) == 0:
        return pd.DataFrame()
    for i, box_score in enumerate(box_scores):
        # find_all duplicates the tables for some reason
        if i % 2 == 1:
            continue
        scores.at[i, "Ongoing"] = False
        rows : List[Soup] = box_score.find_all('tr')
        scores.at[i, "Time"] = " ".join(rows[0].text.split()[1:3])
        scores.at[i, "Attendance"] = rows[0].text.split()[-1]
        # account for games with location info
        if len(rows) == 7:
            info : str = rows[1].text.strip()
            event_location = _event_location(info)
            scores.at[i, "Event"] = event_location[0]
            scores.at[i, "Location"] = event_location[1]
            rows.pop(1) # realign the box scores
        else:
            scores.at[i, "Event"] = "Regular Season"

        away_info : str = rows[1].find_all('td')[1].text.strip()
        home_info : str = rows[-2].find_all('td')[1].text.strip()

        if away_info[0] == '#':
            away_team : str = " ".join(away_info.split(' ')[1:]) #remove seeds from names
            home_team : str = " ".join(home_info.split(' ')[1:])
            scores.at[i, "Away_Seed"] = away_info.split()[0][1]  # get seed
            scores.at[i, "Home_Seed"] = home_info.split()[0][1]
        else:
            away_team = away_info
            home_team = home_info
        # home/away_team is now in the format "team (w-l)"
        scores.at[i, "Away_Team"] = " ".join(away_team.split()[:-1]) #remove record
        scores.at[i, "Home_Team"] = " ".join(home_team.split()[:-1])
        wins_losses : Tuple [str, str] = _wins_and_losses(away_team)
        scores.at[i, "Away_Losses"] = wins_losses[1]
        scores.at[i, "Away_Wins"] = wins_losses[0]
        wins_losses = _wins_and_losses(home_team)
        scores.at[i, "Home_Losses"] = wins_losses[1]
        scores.at[i, "Home_Wins"] = wins_losses[0]

        # If this bool fails, that means their opponent is not an NCAA
        # opponent. Shame on the scheduler!
        if rows[1].find('a'):
            scores.at[i, "Away_id"] = rows[1].find('a')['href'].split('/')[-1]
        else:
            scores.at[i, "Away_Wins"] = pd.NA
            scores.at[i, "Away_Losses"] = pd.NA
            scores.at[i, "Away_Team"] = away_team
        # apparently some teams travel to none ncaa schools to play
        # for some godforsaken reason
        if rows[-2].find('a'):
            scores.at[i, "Home_id"] = rows[-2].find('a')['href'].split('/')[-1]
        else:
            scores.at[i, "Home_Wins"] = pd.NA
            scores.at[i, "Home_Losses"] = pd.NA
            scores.at[i, "Home_Team"] = home_team

        scores.at[i, "Home_Score"] = rows[-2].find_all('td')[-1].text.strip()
        scores.at[i, "Away_Score"] = rows[1].find_all('td')[-1].text.strip()
        # Canceled games mess up formatting and puts the tag in the away_score,
        # and it's easier to just let it run and fix it here
        if scores["Away_Score"][i] == "Canceled" or scores["Away_Score"][i] == "Ppd"\
                or scores["Attendance"][i] == "PM":
            scores.at[i, "Away_Score"] = pd.NA
            scores.at[i, "Home_Score"] = pd.NA
            scores.at[i, "Time"] = pd.NA
            scores.at[i, "Attendance"] = '0'
            scores.at[i, "Event"] = "Canceled"
            scores.at[i, "Location"] = "Canceled"
            continue
        # sometimes no box score is given
        if scores["Attendance"][i] == "Final" or scores["Attendance"][i] == "AM":
            scores.at[i, "Attendance"] = '0'
            continue
        # idk even know how this one gets screwed up but it happens
        if scores["Attendance"][i] == "TBA":
            scores.at[i, "Attendance"] = '0'
            scores.at[i, "Time"] = pd.NA
            continue
        # and sometimes its just totally broken and not worth repairing
        if not scores["Away_Score"][i]:
            scores.at[i, "Away_Score"] = pd.NA
            scores.at[i, "Home_Score"] = pd.NA
            continue

        scores.at[i, "Game_id"] = rows[-1].find('a')['href'].split('/')[2]
        if pd.isna(scores.at[i, "Location"]):
            scores.at[i, "Location"] = scores.at[i, "Home_Team"]
            # just a regular season game
        # detects if game is ongoing
        if scores.at[i, "Game_id"] == "livestream_scoreboards":
            scores.at[i, "Game_id"] = pd.NA
            scores.at[i, "Attendance"] = '0'
            scores.at[i, "Ongoing"] = True
    scores["Division"] = division
    scores["Date"] = date
    return _cleanup(scores)

