# NCAA_basketball_rank
An open source ranking algorthm to rank every NCAA basketball team in the country

Dependencies:
  pandas
  lxml
  beautifulsoup4

This is all the tools needed to create your own college basketball rankings! Feauturing garbage time filtration, full support for all divisions, men and women's, and combatibility going back to 2020. To use it, simply dump the files in the same folder, and import every_rank from full_rankings.py. You will need to define a start date, end date, a csv file, and an optional bool to switch to women's mode. This will return a pandas dataframe of every team in order that they were added to the league, and an associated adjusted offesnive effeciency, defensive effeciency, and effeciency margin. Offensive effeciency is a rough measurement of how many points per possession a team is expected to score against an average team in a division. Defensive effeciency is meaasuring how much you're expected to give up per possession vs an average team. Effeciency margin is simply offesnive - defensive. Please feel free to reach out with any questions, or if you would like to be a contributor. Email is mscheske@umich.edu. Modifying this code to make your own rankings is highly encouraged. 
