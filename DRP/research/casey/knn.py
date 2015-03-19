import os, sys
full_path = os.path.dirname(os.path.realpath(__file__))+"/"
django_path = full_path[:full_path.rfind("/DRP/")]
if django_path not in sys.path:
  sys.path = [django_path] + sys.path
  os.environ['DJANGO_SETTINGS_MODULE'] = 'DRP.settings'


DEBUG = True
PRINT_DETAILS = False


#If `universe is 'None', then the default universe is specified in the metric.
universe = None

# Prepare the metric.
from DRP.recommendation.metrics import get_default_metric
metric = get_default_metric(universe=universe, debug=DEBUG)


from DRP.model_building.rxn_calculator import headers

# The field to use to make sure a point isn't compared to itself.
id_field = "XXXtitle" #TODO: This should change to "ref", but low-priority.
id_index = headers.index(id_field)


distance_cache = {}
def distance(point, other):

  # Cache the distance between points for future use.
  key = (point[id_index], other[id_index])
  reverse_key = (other[id_index], point[id_index])

  if reverse_key in distance_cache:
    return distance_cache[reverse_key]

  else:

    if not key in distance_cache:
      distance_cache[key] = metric(point, other)

    return distance_cache[key]



def filter_out_identical(point, others):
  point_id = point[id_index]
  others = filter(lambda other: other[id_index]!=point_id, others)
  return others


def get_knn_tuples(point, others, k):
  """
  Gather the k closest (point, distance) tuples.
  """

  others = filter_out_identical(point, others)

  neighbors = [(other, distance(point,other)) for other in others]
  neighbors.sort(key=lambda neighbor: neighbor[1])
  return neighbors[:k]


def average_knn_distance(point, others, k):
  """
  Calculate the average distance to the k-nearest neighbors for some `point`.
  """

  knn = get_knn_tuples(point, others, k)
  distances = map(lambda tup: tup[1], knn)
  total = float(sum(distances))

  if PRINT_DETAILS:
    if point[0] in {"jk252.5","jho252.5"} :
      print "{} Nearest Neighbors of {}:".format(k, point[0])
      print "\n".join(["\t{} : {}".format(tup[0][0], tup[1]) for tup in knn])

  return total/len(knn)


def get_research_points():

  from DRP.research.casey.retrievalFunctions import get_data_from_ref_file
  data = get_data_from_ref_file("DRP/research/casey/raw/030915_datums.txt")

  """
  # Used for the seed KNN graphs.
  from DRP.research.casey.retrievalFunctions import get_data_from_ref_file
  data = get_data_from_ref_file("DRP/research/casey/raw/030915_seeds.txt")
  """

  """
  # Used for the average KNN distance calculations.
  from DRP.retrievalFunctions import get_valid_data
  from DRP.retrievalFunctions import filter_by_date

  data = get_valid_data()
  data = filter_by_date(data, "05-21-2014", "before")
  """


  """
  #TODO: quickie-info
  dates = [d.creation_time_dt for d in data]
  dates.sort()
  print "Latest: {}".format(dates[-1])
  print "Earliest: {}".format(dates[0])

  print "Total: {}".format(len(data))
  te = filter(lambda d: "Te" in d.atoms, data)
  se = filter(lambda d: "Se" in d.atoms, data)
  neither = filter(lambda d: not "Te" in d.atoms and not "Se" in d.atoms, data)
  print "Te: {}".format(len(te))
  print "Se: {}".format(len(se))
  print "neither: {}".format(len(neither))
  """

  return data


def get_research_others():
  from DRP.retrievalFunctions import get_valid_data
  from DRP.retrievalFunctions import filter_by_date

  data = get_valid_data()
  data = filter_by_date(data, "05-21-2014", "before")
  data = [d.get_calculations_list(debug=True) for d in data]

  return data


def get_knn_research_results(k_range):

  if DEBUG: print "Gathering research points..."
  points = get_research_points()
  if not points: raise Exception("No research points found!")

  if DEBUG: print "Gathering other research points..."
  others = get_research_others()
  if not others: raise Exception("No \"other\" research points found!")

  results = {k:[] for k in k_range}
  calc_cache = {}

  for k in k_range:
    print "Average k={} distance...".format(k)
    for i, point in enumerate(points):

        # Store the `calculations_list` of each point for speed-up.
        if point not in calc_cache:
          calc_cache[point] = point.get_calculations_list()

        avg_dist = average_knn_distance(calc_cache[point], others, k)
        results[k].append( (point, avg_dist) )

  return results


def calculate_avg_distance(low, high):
  from DRP.graph import get_graph

  k_range = xrange(low, high+1)
  results = get_knn_research_results(k_range)


  for k, reactions in results.items():
    dists = [dist for p, dist in reactions]
    dists.sort()

    # Graph Options
    padding = 0.01 # percent of graph to use as padding.
    num_major_ticks = 10.0
    num_minor_ticks = 50.0

    max_dist = max(dists)
    min_dist = min(dists)

    # Calculate padding for the graph.
    pre_tick_dist = (max_dist-min_dist)/num_major_ticks
    top = max_dist * (1 + pre_tick_dist*padding)
    bottom = min_dist * (1 - pre_tick_dist*padding)
    if bottom<0: bottom = 0

    line = {"K={}".format(k) : dists}
    percentage_baseline = range(len(dists))

    graph = get_graph(line, percentage_baseline,
                        xLabel="# of Reactions",
                        yLabel="Average KNN Distance",
                        tick_range=(bottom, top),
                        major_tick=(top-bottom)/num_major_ticks,
                        minor_tick=(top-bottom)/num_minor_ticks,
                        show_legend=True,
                        show_minor=True,
                        show_mean=True,
                        )

    graph.show()
    raw_input("Press Enter to continue.")


def knn_research_graphs(low, high):
  from DRP.graph import get_graph

  k_range = xrange(low, high+1)
  results = get_knn_research_results(k_range)

  # Sort the reactions and their distances into Se/Te buckets.
  buckets = {"Te":{}, "Se":{}, "Both":{}}

  for k, reactions in results.items():
    for point, dist in reactions:
      if "Te" in point.atoms:
        key = "Te"
      elif "Se" in point.atoms:
        key = "Se"

      if point not in buckets[key]:
        buckets[key][point] = [None for i in k_range]
        buckets["Both"][point] = [None for i in k_range]

      buckets[key][point][k-1] = dist
      buckets["Both"][point][k-1] = dist


  for key, bucket in buckets.items():
    if bucket:
      print "Graphing {}... ({})".format(key, len(bucket))

      # Rename the keys so the lines are identified by the seed "ref".
      bucket = {seed.ref:k_vals for seed, k_vals in bucket.items()}

      # Graph Options
      padding = 0.01 # percent of graph to use as padding.
      num_major_ticks = 10.0
      num_minor_ticks = 50.0

      max_dist = 0.0
      min_dist = float("inf")
      for point, dists in bucket.items():
        for dist in dists:
          if dist>max_dist: max_dist = dist
          if dist<min_dist: min_dist = dist

      # Calculate padding for the graph.
      pre_tick_dist = (max_dist-min_dist)/num_major_ticks
      top = max_dist * (1 + pre_tick_dist*padding)
      bottom = min_dist * (1 - pre_tick_dist*padding)
      if bottom<0: bottom = 0

      graph = get_graph(bucket, list(k_range),
                        xLabel="# Nearest Neighbors (K)",
                        yLabel="Average KNN Distance",
                        tick_range=(bottom, top),
                        major_tick=(top-bottom)/num_major_ticks,
                        minor_tick=(top-bottom)/num_minor_ticks,
                        show_legend=True,
                        show_minor=True
                        )
      graph.show()
      raw_input("Press Enter to continue...")
    else:
      print "Skipping empty bucket `{}`...".format(key)

def matrix_to_csv(matrix, filename):
  import csv
  with open(filename,"w") as f:
    writer = csv.writer(f)
    for line in matrix:
      writer.writerow(line)

  print "'{}' written!".format(filename)


def make_distance_csv(low, high):
  k_range = xrange(low, high+1)
  results = get_knn_research_results(k_range)

  final = {}

  for k, point_tups in results.items():
    for point, dist in point_tups:

      if point not in final: final[point] = {
        "outcome":point.outcome,
        "ref": point.ref,
      }

      final[point]["k={}".format(k)] = dist

  columns = sorted(final[final.keys()[0]].keys(), reverse=True)

  matrix = [columns]
  matrix += [[calcs[col] for col in columns] for point, calcs in final.items()]

  filename = "{}/DRP/research/casey/results/knn_calculations.csv".format(django_path)
  matrix_to_csv(matrix, filename)





def main():
  #knn_research_graphs(1,20)
  #calculate_avg_distance(1,20)
  make_distance_csv(1,15)

if __name__=="__main__":
  main()

