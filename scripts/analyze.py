import os.path
import json
from collections import defaultdict
from collections import namedtuple
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import copy

REGION = "PRO"
CHAMPIONS = {}
ITEMS = {}
NUM_GAMES = 100

BOOTS = set([3006, 3009, 3020, 3047, 3111, 3117, 3158])
CONSUMABLES = set(range(3340, 3343) + range(3361, 3365) + [2043, 2044, 2003, 2004]) 

# Sated devourers are mapped to the corresponding devourer, sightstone, manamune, archangel
ENCHANTMENT_MAP = {3930: 3710, 3931: 3718, 3932: 3722, 3933: 3726, 2045: 2049, 3042: 3004, 3040: 3003}
EXEMPT_NON_FINAL_ITEMS = set([3710, 3718, 3722, 3726, 2049, 3004, 3003]) # Devourer items, sightstone


def convert(dictionary):
    return namedtuple('GenericDict', dictionary.keys())(**dictionary)

def load_champions():
	filename = os.path.join("data", 'champion.json')
	with open(filename) as infile:
		x = json.load(infile)
	
	for c in x['data']:
		CHAMPIONS[int(x['data'][c]['key'])] = convert(x['data'][c])

def load_items():
	filename = os.path.join("data", 'item.json')
	with open(filename) as infile:
		x = json.load(infile)

	for c in x['data']:
		d = x['data'][c]
		if 'from' in d:
			d['made_from'] = d['from']
			del d['from']
		else:
			d['made_from'] = []
		ITEMS[int(c)] = convert(d)

	item_names = {}
	for k,v in ITEMS.iteritems():
		item_names[str(k)] = v.name
	with open(os.path.join("..", "data", "results", "item_names.json"), 'wb') as outfile:
		json.dump(item_names, outfile)
		

def get_games(start, count):
	filename = os.path.join("data", '%s-%d.json' % (REGION, start))
	with open(filename) as infile:
		x = json.load(infile)
	return x

def normalize_item(item_id):
	if item_id not in ITEMS:
		return None

	item = ITEMS[item_id]
	
	if len(item.made_from) == 1 and int(item.made_from[0]) in BOOTS:

		return int(item.made_from[0])
	elif 'Consumable' in item.tags:
		return None
	elif item_id in CONSUMABLES:
		return None
	elif item_id in ENCHANTMENT_MAP:
		return ENCHANTMENT_MAP[item_id]
	elif item_id in EXEMPT_NON_FINAL_ITEMS:
		return item_id
	elif len(item.into) > 0:


		# Not final item
		return None
	elif item.gold["total"] < 500:
		return None
	else:
		return item_id


CHAMP_STATS = defaultdict(lambda: [0, 0, 0, 0]) # AD / AP / True

def analyze_solo_match(match):
	champ_for_participant = {}
	for p in match['participants']:
		champ_for_participant[p['participantId']] = p['championId']
		stats = p['stats']

		champ_id = p['championId']
		CHAMP_STATS[champ_id][0] += stats['physicalDamageDealtToChampions']
		CHAMP_STATS[champ_id][1] += stats['magicDamageDealtToChampions']
		CHAMP_STATS[champ_id][2] += stats['trueDamageDealtToChampions']
		CHAMP_STATS[champ_id][3] += 1

def analyze_match(match):
	team_stats = defaultdict(lambda: [0, 0, 0]) # AD / AP / True
	for p in match['participants']:
		stats = p['stats']
		team_id = p['teamId']
		team_stats[team_id][0] += stats['physicalDamageDealtToChampions']
		team_stats[team_id][1] += stats['magicDamageDealtToChampions']
		team_stats[team_id][2] += stats['trueDamageDealtToChampions']

	normalized = [] 
	for ad, ap, true in team_stats.values():
		total = float(ad + ap + true)
		normalized.append([ad / total, ap / total])
	return normalized, team_stats

def get_dmg_centers():
	
	data = []
	for i in xrange(120):
		print i
		games = get_games(i * NUM_GAMES, NUM_GAMES)
		for g in games:
			data.extend(analyze_match(g)[0])
	

	k_means = KMeans(init='k-means++', n_clusters = 3, n_init=10)
	k_means.fit(data)
	print k_means.cluster_centers_


	plt.figure(2, figsize=(4, 4))
	plt.clf()

	# Plot the training points
	colors = ['r', 'g', 'b']

	for d in data:
		plt.scatter(d[0], d[1], color=colors[k_means.predict(d)][0])
	plt.xlabel('AD')
	plt.ylabel('AP')

	plt.xlim(0, 1)
	plt.ylim(0, 1)
	plt.xticks(())
	plt.yticks(())
	plt.show()

DEFENCE_TAGS = {'ad': set(['Armor', 'SpellBlock', 'Health']), 'ap': set(['Armor', 'SpellBlock', 'Health']), 'mixed': set(['Armor', 'SpellBlock', 'Health'])}

def get_dmg_type(stats):
	centers = [[ 0.48269258,  0.45876403 ],
 				[ 0.34298586,  0.60917522],
 				[ 0.62638547,  0.31306683]]
 	center_labels = ['mixed', 'ap', 'ad']
	ad, ap, true = stats
	total = float(ad + ap + true)
	ad_ratio = ad / total
	ap_ratio = ap / total

	min_diff = 10000000
	min_index = 0
	for i in xrange(3):
		center = centers[i]
		d = (ad_ratio - center[0])**2 + (ap_ratio - center[1])**2 
		if d < min_diff:
			min_index = i
			min_diff = d
	return center_labels[min_index]


def get_defence_items():
	
 	# { champId: {support: {ap: { itemId: 0, ..., count = 0}, ad: {}, mixed: {}} } ...}
	data = defaultdict(lambda: defaultdict(lambda: {'ap': defaultdict(lambda: 0.01), 'ad': defaultdict(lambda: 0.01), 'mixed': defaultdict(lambda: 0.01), 'total': 0.01}))
	for i in xrange(120):
		print i
		games = get_games(i * NUM_GAMES, NUM_GAMES)
		for g in games:
			_, team_stats = analyze_match(g)
			team_ids = team_stats.keys()
			roles = get_role_type(g)

			for team_id, stats in team_stats.iteritems():
				# what does enemy bulid against this damage
				dmg_type = get_dmg_type(stats)
				enemy_team_id = team_ids[0] if team_ids[0] != team_id else team_ids[1]
				

				for p in g['participants']:
					if p['teamId'] == enemy_team_id:
						role = roles[p['participantId']]
						for i in xrange(7):
							item_id = p['stats']['item%d' % i]
							item_id = normalize_item(item_id)
							if item_id == None:
								continue

							item = ITEMS[item_id]

							is_defence = False
							for t in item.tags:
								if t in DEFENCE_TAGS[dmg_type]:
									is_defence = True
									break
							if is_defence:
								data[p['championId']][role][dmg_type][item_id] += 1
						data[p['championId']][role][dmg_type]['total'] += 1
						data[p['championId']][role]['total'] += 1
	total_champs = 0
	
	for champ_id in data:
		
		champ = CHAMPIONS[champ_id]
		print champ.name
		for role in ['carry', 'support', 'jungle']:
			print "\t%s games: %d" % (role, data[champ_id][role]['total'])
			total_champs += int(data[champ_id][role]['total'])


			for dmg_type in ['ad', 'ap']:
				print "\t\t%s" % dmg_type
				for item_id in data[champ_id][role][dmg_type].keys():
					if item_id == 'total': continue
					ad_pick_rate = float(data[champ_id][role]['ad'][item_id]) / data[champ_id][role]['ad']['total'] * 100
					ap_pick_rate = float(data[champ_id][role]['ap'][item_id]) / data[champ_id][role]['ap']['total'] * 100
					mixed_pick_rate = float(data[champ_id][role]['mixed'][item_id]) / data[champ_id][role]['mixed']['total'] * 100

					if dmg_type == 'ad':
						if ad_pick_rate > 5 and ad_pick_rate > mixed_pick_rate and mixed_pick_rate > ap_pick_rate:
							item = ITEMS[item_id]
							print "\t\t\t%s: %.2f" % (item.name, float(data[champ_id][role][dmg_type][item_id]) / data[champ_id][role][dmg_type]['total'] * 100), ad_pick_rate, mixed_pick_rate, ap_pick_rate
						else:
							if item_id in data[champ_id][role][dmg_type]:
								del data[champ_id][role][dmg_type][item_id]
					else:
						if ap_pick_rate > 5 and ap_pick_rate > mixed_pick_rate and mixed_pick_rate > ad_pick_rate:
							item = ITEMS[item_id]
							print "\t\t\t%s: %.2f" % (item.name, float(data[champ_id][role][dmg_type][item_id]) / data[champ_id][role][dmg_type]['total'] * 100), ad_pick_rate, mixed_pick_rate, ap_pick_rate
						else:
							if item_id in data[champ_id][role][dmg_type]:
								del data[champ_id][role][dmg_type][item_id]

	with open(os.path.join("output", "defence_items.json"), 'wb') as outfile:
		json.dump(data, outfile)

def get_role_centers():
	data = []
	for i in xrange(120):
		print i
		games = get_games(i * NUM_GAMES, NUM_GAMES)
		for g in games:
			for team in g['teams']:
				team_id = team['teamId']
				minions_killed = []
				neutrual_minions_killed = []
				for p in g['participants']:
					minions_killed.append(p['stats']['minionsKilled'])
					neutrual_minions_killed.append(p['stats']['neutralMinionsKilled'])
				total_minions_killed = max(float(sum(minions_killed)), 1.0)
				total_neutral_minions_killed = max(float(sum(neutrual_minions_killed)), 1.0)

				for i in xrange(len(minions_killed)):
					data_point = (minions_killed[i] / total_minions_killed, neutrual_minions_killed[i] / total_neutral_minions_killed)
					data.append(data_point)

	k_means = KMeans(init='k-means++', n_clusters = 3, n_init=10)
	k_means.fit(data)
	print k_means.cluster_centers_


	plt.figure(2, figsize=(12, 8))
	plt.clf()

	# Plot the training points
	colors = ['r', 'g', 'b']
	clusters = [[], [], []]

	for d in data:
		cluster = k_means.predict(d)[0]
		clusters[cluster].append(d)
	for i in xrange(3):
		cluster = clusters[i]
		plt.scatter([c[0] for c in cluster], [c[1] for c in cluster], color=colors[i])

	plt.xlabel('minion CS %')
	plt.ylabel('jungle CS %')

	plt.xlim(0, 1)
	plt.ylim(0, 1)
	plt.xticks(())
	plt.yticks(())
	plt.show()


def get_role_type(match):
	centers = [[ 0.15063603,  0.05032667],
 				[ 0.03084382,  0.34990775],
 				[ 0.02345441,  0.00376929]]

 	center_labels = ['carry', 'jungle', 'support']

 	data = {}
 	for team in match['teams']:
		team_id = team['teamId']
		minions_killed = []
		neutrual_minions_killed = []
		for p in match['participants']:
			minions_killed.append(p['stats']['minionsKilled'])
			neutrual_minions_killed.append(p['stats']['neutralMinionsKilled'])
		total_minions_killed = max(float(sum(minions_killed)), 1.0)
		total_neutral_minions_killed = max(float(sum(neutrual_minions_killed)), 1.0)

		for i in xrange(len(minions_killed)):
			p = match['participants'][i]
			data_point = (minions_killed[i] / total_minions_killed, neutrual_minions_killed[i] / total_neutral_minions_killed)

			min_diff = 100000
			min_index = 0
			for i in xrange(3):
				center = centers[i]
				d = (data_point[0] - center[0])**2 + (data_point[1] - center[1])**2 
				if d < min_diff:
					min_index = i
					min_diff = d

			data[p['participantId']] = center_labels[min_index]
	return data


	

def get_role_items():

	data = defaultdict(lambda: {'jungle': defaultdict(lambda: 0.01), 'support': defaultdict(lambda: 0.01), 'carry': defaultdict(lambda: 0.01), 'total': 0.01})
	for i in xrange(120):
		print i
		games = get_games(i * NUM_GAMES, NUM_GAMES)
		for g in games:
			roles = get_role_type(g)

			for p in g['participants']:
				role = roles[p['participantId']]

				for i in xrange(7):
					item_id = p['stats']['item%d' % i] 
					if item_id not in ITEMS:
						continue
					item_id = normalize_item(item_id)	
					if item_id == 3170:
						import pdb; pdb.set_trace()
					if item_id == None:
						continue

					item = ITEMS[item_id]
					if item_id == None:
						# Not a completed item
						continue

					data[p["championId"]][role][item_id] += 1
				data[p["championId"]][role]["total"] += 1
				data[p["championId"]]["total"] += 1


	for champ_id in data:
		champ = CHAMPIONS[champ_id]
		print champ.name, "games: %d" % data[champ_id]['total']
		for role in ['jungle', 'support', 'carry']:
			print "\t%s, games: %d" % (role, data[champ_id][role]['total'])
			for item_id in data[champ_id][role]:
				if item_id == 'total':
					continue
				item = ITEMS[item_id]
				print "\t\t%s: %.2f" % (item.name, data[champ_id][role][item_id] / data[champ_id][role]['total'])

	with open(os.path.join("output", "ending_items.json"), 'wb') as outfile:
		json.dump(data, outfile)

def normalize_start_item(item_id):
	if item_id == 2010:
		return 2003
	else:
		return item_id


def get_starting_items():
	data = defaultdict(lambda: {'jungle': defaultdict(lambda: 0.01), 'support': defaultdict(lambda: 0.01), 'carry': defaultdict(lambda: 0.01), 'total': 0.01})
	for i in xrange(120):
		print i
		games = get_games(i * NUM_GAMES, NUM_GAMES)
		for g in games:
			roles = get_role_type(g)

			champs_selected = {p['participantId'] : p['championId'] for p in g['participants']}

			items_bought = defaultdict(lambda: defaultdict(int))

			for frame in g['timeline']['frames']:
				if frame['timestamp'] > 120000:
					break
				if 'events' not in frame:
					continue
				for event in frame['events']:
					if event['eventType'] == 'ITEM_PURCHASED':
						item_id = normalize_start_item(event['itemId'])
						items_bought[event['participantId']][item_id] += 1
					elif event['eventType'] == 'ITEM_UNDO':
						item_id = normalize_start_item(event['itemBefore'])
						items_bought[event['participantId']][item_id] -= 1
					elif event['eventType'] == 'ITEM_SOLD':
						item_id = normalize_start_item(event['itemId'])
						items_bought[event['participantId']][item_id] -= 1

			for participant_id, items in items_bought.iteritems():
				role = roles[participant_id]
				hashed_items = tuple(sorted(items.items()))
				data[champs_selected[participant_id]][role][hashed_items] += 1

	formatted = {}

	for champ_id in data:
		champ = CHAMPIONS[champ_id]
		print champ.name
		for role in ['jungle', 'support', 'carry']:
			print "\t%s" % (role)
			for starting_items in data[champ_id][role]:
				print "\t\t%d" % data[champ_id][role][starting_items]
				for item_id, count in starting_items:
					if item_id not in ITEMS:
						continue
					item = ITEMS[item_id]
					print "\t\t\t%s, %d" % (item.name, count)

	for champ_id in data:
		formatted[champ_id] = {"jungle": [], "support": [], "carry": []}
		for role in formatted[champ_id]:
			sorted_item_sets = sorted([(int(v), k) for k, v in data[champ_id][role].iteritems()], reverse=True)
			if len(sorted_item_sets) > 3:
				sorted_item_sets = sorted_item_sets[:3]
			formatted[champ_id][role] = tuple(sorted_item_sets)

	with open(os.path.join("output", "starting_items.json"), 'wb') as outfile:
		json.dump(formatted, outfile)

load_champions()
load_items()
if __name__ == "__main__":
	pass
	# get_dmg_centers()
	# get_role_centers()
	# get_defence_items()


	# get_role_items()
	# get_starting_items()
