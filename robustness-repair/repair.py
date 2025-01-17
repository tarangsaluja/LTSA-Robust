import subprocess
import os
from os import path
from random import random
import shutil
import DESops as d
import igraph
from lts import StateMachine
import itertools

this_file = path.dirname(path.abspath(__file__))


# Definition of priority
PRIORITY0 = 0
PRIORITY1 = 1
PRIORITY2 = 2
PRIORITY3 = 3

class Repair:
    def __init__(self, sys, env_p, safety, preferred, progress, alphabet, controllable, observable, verbose=False):
        self.verbose = verbose
        if path.exists("tmp"):
            shutil.rmtree("tmp")
        os.mkdir("tmp")

        # cache for fsp to lts
        self.fsp_cache = {}
        # cache for satisfied preferred behavior w.r.t some controllable and observable events
        self.check_preferred_cache = {}
        # cache for controller synthesis result w.r.t some controllable and observable events
        self.synthesize_cache = {}

        # the model files of the system
        self.sys = list(map(lambda x: self.fsp2lts(x), sys))
        # the model files of the deviated environment model
        self.env_p = list(map(lambda x: self.fsp2lts(x), env_p))
        # the model files of the safety property
        self.safety = list(map(lambda x: self.fsp2lts(x), safety))
        # a map from priority to model files of the preferred behavior
        self.preferred = preferred
        # a list of events as progress property
        self.progress = list(map(lambda x: self.make_progress_prop(x), progress))
        # a list of events for \alpha M \cup \alpha E
        self.alphabet = alphabet
        # a map from cost to list of controllable events
        self.controllable = controllable
        # a map from cost to list of observable events
        self.observable = observable

        # TODO:
        # assert controllable should be a subset of observable
        # assert False, "Controllable should be a subset of observable"
        # assert observable is a subset of alphabet
        # assert False, "Observable events should be a subset of the alphabet
        # assert False, "For the same event e, cost of Ac(a) > cost of Ao(a)"
    
    def _synthesize(self, controllable, observable):
        """
        Given a set of preferred behavior, controllable events, and observable events,
        this function returns a controller by invoking DESops. None is returned when
        no such controller can be found.
        """
        key = (tuple(controllable), tuple(observable))
        if key in self.synthesize_cache:
            if self.verbose:
                print("Synthesize cache hit: ", key)
            return self.synthesize_cache[key]

        plant = list(map(lambda x: self.lts2fsm(x, controllable, observable), self.sys + self.env_p))
        plant = d.composition.parallel(*plant)
        p = list(map(lambda x: self.lts2fsm(x, controllable, observable, extend_alphabet=True), self.safety))
        p = p + self.progress
        p = p[0] if len(p) == 1 else d.composition.parallel(*p)

        L = d.supervisor.supremal_sublanguage(plant, p, prefix_closed=False, mode=d.supervisor.Mode.CONTROLLABLE_NORMAL)
        L = d.composition.observer(L)

        # return the constructed controller which is admissible and redundant
        self.synthesize_cache[key] = self.construct_supervisor(plant, L, controllable, observable) if len(L.vs) != 0 else None
        return self.synthesize_cache[key]
    
    def remove_unnecessary(self, sup, controllable, observable):
        """
        Given a plant, controller, controllable events, and observable events, remove unnecessary
        controllable/observable events to minimize its cost.
        """
        all_states = sup.all_states()
        out_trans = sup.out_trans()

        can_uc = observable.copy()
        for s in all_states:
            for a in can_uc.copy():
                if sup.next_state(s, a) == None:
                    can_uc.remove(a)
        can_uo = can_uc.copy()
        for s in all_states:
            for a in can_uo.copy():
                if [s, sup.alphabet.index(a), s] not in out_trans[s]:
                    can_uo.remove(a)
        min_controllable = set(controllable) - set(can_uc)
        min_observable = set(observable) - set(can_uo)

        # Hide unobservable events
        sup = self.lts2fsm(sup, min_controllable, min_observable, name="sup")
        sup = d.composition.observer(sup)

        return sup, min_controllable, min_observable
    
    def next_possible_min_events(self, last_gp_list, controllable_rm, observable_rm):
        p_list = [] # start the new list of possibilities
        # iterate through good possibilities from last iteration
        for event_dict in last_gp_list:
            # look at all controllable actions in the priority and remove when possible to create new minimization
            for c in controllable_rm:
                if c in event_dict["c"] and len(event_dict["c"]) > 1: # avoid removing all controllable
                    new_controllable = event_dict["c"].copy()
                    new_controllable.remove(c)
                    new_event_dict = {"c": new_controllable, "o": event_dict["o"]}
                    p_list.append(new_event_dict)
            # look at all observable actions in the priority and remove when possible to create minimization
            for o in observable_rm:
                if o in event_dict["o"] and o not in event_dict["c"]:
                    new_observable = event_dict["o"].copy()
                    new_observable.remove(o)
                    new_event_dict = {"c": event_dict["c"], "o": new_observable}
                    p_list.append(new_event_dict)

        # remove duplicates
        cp_list = []
        for event_dict in p_list:
            if event_dict not in cp_list:
                cp_list.append(event_dict)
        
        return cp_list
    
    def minimize(self, minS, controllable, observable, preferred):
        """
        Given some set of controllable and observable events and supervisor,
        minimize the supervisor and returns the set of controllable and observable
        events with the minimal cost, needed for the given preferred behavior
        """        
        # parition all events that can be made controllable and/or observable into lists by priority (cost)
        high_cost_controllable = [c for c in controllable if c in self.controllable[PRIORITY3]] # High cost controllable events
        medium_cost_controllable = [c for c in controllable if c in self.controllable[PRIORITY2]] # Medium cost controllable events
        low_cost_controllable = [c for c in controllable if c in self.controllable[PRIORITY1]] # Low cost controllable events
        
        high_priority_observable = [o for o in observable if o in self.observable[PRIORITY3]] # High cost Observable Events
        medium_priority_observable = [o for o in observable if o in self.observable[PRIORITY2]] # Medium cost Observable Events
        low_priority_observable = [o for o in observable if o in self.observable[PRIORITY1]] # Low cost Observable Events

        # Dictionary where events are separated according to priority
        # Key is 0, 1, or 2 where 0 is high cost, 1 is medium cost, and 2 is low cost
        # Value is a list of list where first list is controllable events and the second list is observable events 
        actions_dict = {
            0: [high_cost_controllable, high_priority_observable],
            1: [medium_cost_controllable, medium_priority_observable], 
            2: [low_cost_controllable, low_priority_observable]
        }

        # initialize last_gp_list, it is a placeholder which saves the last set of possible minimizations
        # that passed if at some interation there are no minimizations that pass
        last_gp_list = []
        # gp_list is the set of good possibilities, initialize with nothing removed as a good possibility
        gp_list = [{"c": set(controllable), "o": set(observable), "minS": minS}]

        # By iterating i in range(3) we examine first the high cost events, then medium cost events, and then low cost events
        for i in range(3):
            # initialize the number of iterations when dealing with a priority group
            j = 0
            # continue adding events of a priority until it provides to be futile or it is impossible to add more
            while (len(gp_list) != 0 and j < (len(actions_dict[i][0]) + len(actions_dict[i][1]))):
                j = j + 1 # iterate the counter for how many events have been removed of the current priority

                last_gp_list = gp_list # save the gp_list, the list of good possibilities from the last iteration
                p_list = self.next_possible_min_events(last_gp_list, actions_dict[i][0], actions_dict[i][1])    
                gp_list = [] # initialize gp_list
                # keep only the minimizations which work
                for event_dict in p_list:
                    if self.verbose:
                        print("Minimizing with...")
                        print("\tEc:", event_dict["c"])
                        print("\tEo:", event_dict["o"])
                    # synthesize with the appropriate controllable/observable events
                    minS = self._synthesize(event_dict["c"], event_dict["o"]) 
                    if minS == None:
                        continue
                    minS = self.lts2fsm(minS, event_dict["c"], event_dict["o"])
                    # add minimization if preferred behavior maintained
                    if set(self.check_preferred(minS, event_dict["c"], event_dict["o"], preferred)) == preferred:
                        event_dict["minS"] = minS #update the minS
                        gp_list.append(event_dict) 

            # if while loop was broken because no permissible minimization happened,
            # then use the saved minimizations as the best previous
            if len(gp_list) == 0:
                gp_list = last_gp_list

        return map(lambda x: (x["minS"], x["c"], x["o"]), gp_list)
        # # take one randomly once out of while loop
        # best_minimization = gp_list.pop()
        # # return the appropriate information
        # return best_minimization["minS"], list(best_minimization["c"]), list(best_minimization["o"])

    def construct_supervisor(self, plant, sup_plant, controllable, observable):
        # Convert Sp/G to a StateMachine object
        sup_plant = self.fsm2lts(sup_plant, observable)
        # Hide the unobservable events in the plant and convert it to StateMachine object
        plant = d.composition.observer(plant)
        plant = self.fsm2lts(plant, observable)

        qc, qg = [0], [0]
        new_trans = sup_plant.transitions.copy()
        visited = set()
        while len(qc) > 0:
            sc, sg = qc.pop(0), qg.pop(0)
            if sc in visited:
                continue
            visited.add(sc)
            for a in observable:
                sc_p = sup_plant.next_state(sc, a) # assuming Sp/G and plant are deterministic
                sg_p = plant.next_state(sg, a)
                if sc_p != None:
                    qc.append(sc_p)
                    qg.append(sg_p)
                elif a not in controllable: # uncontrollable event, make admissible
                    new_trans.append([sc, sup_plant.alphabet.index(a), sc])
                elif sg_p == None: # controllable but not defined in G, make redundant
                    new_trans.append([sc, sup_plant.alphabet.index(a), sc])
        return StateMachine("sup", new_trans, sup_plant.alphabet, sup_plant.accept)
    
    def compute_weights(self):
        """
        Given the priority ranking that the user provides, compute the positive utilities for preferred behavior
        and the negative cost for making certain events controllable and/or observable. Return dictionary with this information
        and also returns list of weights for future reference.
        """
        #maintain dictionary for preferred, controllable, and observable
        preferred_dict = self.preferred
        controllable_dict = self.controllable
        observable_dict = self.observable
        alphabet = self.alphabet
        preferred = []
        for key in self.preferred:
            for beh in self.preferred[key]:
                preferred.append(beh)

        #initialize weight dictionary
        weight_dict = {} 
        for i in alphabet:
            weight_dict[i] = ["c", "o"]
        for i in preferred:
            weight_dict[i] = "d"

        #insert behaviors that have no cost into dictionary of weights
        for i in controllable_dict[PRIORITY0]:
            weight_dict[i][0] = 0
        for i in observable_dict[PRIORITY0]:
            weight_dict[i][1] = 0
        
        #intialize list of pairs with polar opposite costs
        category_list = []
        category_list.append([preferred_dict[PRIORITY1], controllable_dict[PRIORITY1], observable_dict[PRIORITY1]]) #first category
        category_list.append([preferred_dict[PRIORITY2], controllable_dict[PRIORITY2], observable_dict[PRIORITY2]]) #second category
        category_list.append([preferred_dict[PRIORITY3], controllable_dict[PRIORITY3], observable_dict[PRIORITY3]]) #third category

        #initialize weights for tiers and list of weight absolute values that are assigned
        total_weight = 0

        #assign weights and grow the weight list
        #give poistive weights to first list in category and negative weights to second list in category
        #compute new weight in order to maintain hierarchy by storing absolute value sum of previous weights
        for i in category_list:
            curr_weight = total_weight + 1
            for j in range(len(i)):
                if j == 0:
                    for k in i[j]:
                        weight_dict[k] = curr_weight
                        total_weight += curr_weight
                elif j == 1:
                    for k in i[j]:
                        weight_dict[k][0] = -1*curr_weight
                        total_weight += curr_weight
                else:
                    for k in i[j]:
                        weight_dict[k][1] = -1*curr_weight
                        total_weight += curr_weight
    
        #return weight_dict, weight_list
        return weight_dict
    
    def compute_util_cost(self, preferred_behavior, min_controllable, min_observable, weight_dict):
        """
        Given preferred behaviors, minimum list of observable behavior, minimum list of controllable behavior, 
        and the weight dictionary, compute the utility of the preferred behavior and the cost separately. 
        """
        #initialize cost and utility
        preferred = sum(map(lambda x: weight_dict[x], preferred_behavior))
        cost = sum(map(lambda x: weight_dict[x][0], min_controllable)) +\
               sum(map(lambda x: weight_dict[x][1], min_observable))        
        return preferred, cost 
    
    def check_preferred(self, minS, controllable, observable, preferred):
        """
        Given some minimum supervisor, a set of controllable events, a set of observable events, 
        and a set of preferred behavior, checks how much preferred behavior is satisfied
        """
        fulfilled_preferred = []

        M_prime = self.compose_M_prime(minS, controllable, observable)

        env = list(map(lambda x: self.lts2fsm(x, controllable, observable), self.env_p))
        env = env[0] if len(env) == 1 else d.composition.parallel(*env)
        M_prime = d.composition.parallel(M_prime, env)

        for p in preferred:
            key = (tuple(controllable), tuple(observable), p)
            if key in self.check_preferred_cache:
                if self.check_preferred_cache[key]:
                    fulfilled_preferred.append(p)
                    if self.verbose:
                        print("Check preferred cache hit:", key)
                continue
            self.check_preferred_cache[key] = False

            p_fsm = self.fsp2fsm(p, controllable, observable)
            M_prime.Euo = p_fsm.Euo.union(M_prime.events - p_fsm.events)
            M_prime.Euc = p_fsm.Euc.union(M_prime.events - p_fsm.events)
            M_prime_observed = d.composition.observer(M_prime) # seems to have performance issue :C
            if d.compare_language(d.composition.parallel(M_prime_observed, p_fsm), p_fsm):
                fulfilled_preferred.append(p)
                self.check_preferred_cache[key] = True

        return fulfilled_preferred
    
    def next_least_to_remove(self, D_max):
        # trim out the preferred behaviors that could never be satisfied
        l1 = [d for d in self.preferred[PRIORITY1] if d in D_max]
        l2 = [d for d in self.preferred[PRIORITY2] if d in D_max]
        l3 = [d for d in self.preferred[PRIORITY3] if d in D_max]
        for i in range(len(l3) + 1):
            for j in range(len(l2) + 1):
                for k in range(len(l1) + 1):
                    print(f"Weaken the preferred behavior by {i} Essential, {j} Important, and {k} Minor...")
                    D_rm_set = []
                    # for this partition of lost behavior, find all possible subsets from each category
                    beh_1_subsets = itertools.combinations(l1, k)
                    beh_2_subsets = itertools.combinations(l2, j)
                    beh_3_subsets = itertools.combinations(l3, i)
                    for l in beh_1_subsets:
                        for m in beh_2_subsets:
                            for o in beh_3_subsets:
                                D_rm_set.append(l + m + o)
                    yield D_rm_set
            
    def synthesize(self, n):
        """
        Given maximum number n of depth to search, return a list of solutions, prioritizng fulfillment of preferred behavior.
        """
        # collect all preferred behavior
        preferred = []
        for key in self.preferred:
            preferred.extend(self.preferred[key])

        # find dictionary of weights by actions, preferred behavior and weights assigned by tiers
        weight_dict = self.compute_weights()

        # first synthesize with all aphabet, then find supervisor, then remove unecessary actions, and check which preferred behavior are satisfied
        alphabet = self.alphabet
        sup = self._synthesize(alphabet, alphabet)
        if sup == None:
            print("Warning: Hard constraint progress property cannot be satisfied.")
            return []
        minS, controllable, observable = self.remove_unnecessary(sup, alphabet, alphabet)
        D_max = self.check_preferred(minS, controllable, observable, preferred)
        print("Maximum fulfilled preferred behavior:", D_max)

        # initialize list of controllers
        controllers = []
        # initialize the least cost experienced overall as a very negative cost, this stands for -infinity
        min_cost = -1_000_000_000
        # intialize number of controllers considered
        t = 0
        for D_rm_sets in self.next_least_to_remove(D_max):
            if t >= n:
                break
            t += 1
            # initialize the best cost for this amount of preferred behaviornot satisfied to be a very negative cost, this stands for -infinity
            min_cost_bracket = -1_000_000_000
            possible_controllers = []
            for remove_behavior in D_rm_sets:
                # remove behavior that we don't care about anymore
                D_max_subset = set(D_max) - set(remove_behavior)
                # find result that is found by minimizing
                for sup, min_controllable, min_observable in self.minimize(minS, controllable, observable, D_max_subset):
                    # compute the total utility and the cost of such a minimization
                    # FIXME: cost only need to compute once
                    utility_preferred, cost = self.compute_util_cost(D_max_subset, min_controllable, min_observable, weight_dict)
                    # check how cost of of this set of removed preferred behavior compares with the best cost thus far
                    if cost < min_cost_bracket: # if cost is worse than best, then ignore it
                        continue
                    else:
                        result = {
                            "M_prime": sup,
                            "controllable": min_controllable,
                            "observable": min_observable, 
                            "preferred": D_max_subset,
                            "preferred_utility": utility_preferred,
                            "cost": cost
                        }
                        if cost > min_cost_bracket: # if cost is better, then clear out all others, update best cost and then start a new list
                            min_cost_bracket = cost
                            possible_controllers = [result]
                        else: # if cost is same as best, then add to list
                            possible_controllers.append(result)
            # if the best cost among these subsets exceeds prior best cost add to controllers 
            if min_cost_bracket > min_cost:
                min_cost = min_cost_bracket
                controllers.extend(possible_controllers)
                for c in possible_controllers:
                    print("New pareto-optimal found:")
                    print("\tEc:", c["controllable"])
                    print("\tEo:", c["observable"])
                    print("\tPreferred:", c["preferred"])
                    print("\tPreferred Utility:", c["preferred_utility"])
                    print("\tCost:", c["cost"])
            else:
                print("No new pareto-optimal solution found.")

        # composes Mprime for all once we know that these are what we want and updates
        for controller in controllers:
            controller["M_prime"] = self.compose_M_prime(controller["M_prime"], controller["controllable"], controller["observable"])

        # returns all controllers
        return controllers

    def compose_M_prime(self, sup, controllable, observable):
        """
        Given a controller in fsm object, compose it with the original system M to get the new design M'
        """
        M = list(map(lambda x: self.lts2fsm(x, controllable, observable), self.sys))
        M = M[0] if len(M) == 1 else d.composition.parallel(*M)
        # FIXME: when sup is an empty controller, it returns a Graph object instead of DFA
        if type(sup) == igraph.Graph:
            M_prime = d.DFA()
            M_prime.events = M.events.copy()
            M_prime.Euc = M.Euc.copy()
            M_prime.Euo = M.Euo.copy()
            return M_prime
        M_prime = d.composition.parallel(M, sup)
        return M_prime
    
    def make_progress_prop(self, e):
        fsm = "2\n\n" +\
              "State0\t0\t1\n" +\
              f"{e}\tState1\tc\to\n\n" +\
              "State1\t1\t1\n" +\
              f"{e}\tState1\tc\to\n"
        with open(f"tmp/{e}.fsm", "w") as f:
            f.write(fsm)
        return d.read_fsm(f"tmp/{e}.fsm")

    def file2fsm(self, file, controllable, observable, extend_alphabet=False):
        name = path.basename(file)
        if file.endswith(".lts"):
            return self.fsp2fsm(file, controllable, observable, extend_alphabet)
        elif file.endswith(".fsm"):
            if extend_alphabet:
                m = StateMachine.from_fsm(file)
                return self.lts2fsm(m, controllable, observable, extend_alphabet=extend_alphabet, name=name)
            else:
                return d.read_fsm(file)
        elif file.endswith(".json"):
            m = StateMachine.from_json(file)
            return self.lts2fsm(m, controllable, observable, extend_alphabet=extend_alphabet, name=name)
        else:
            raise Exception("Unknown input file type")
    
    def lts2fsm(self, m, controllable, observable, name=None, extend_alphabet=False):
        if extend_alphabet:
            m = m.extend_alphabet(self.alphabet)
        tmp = f"tmp/{name}.fsm" if name != None else f"tmp/tmp.{random() * 1000_000}.fsm"
        m.to_fsm(controllable, observable, tmp)
        return d.read_fsm(tmp)

    def fsp2fsm(self, file, controllable, observable, extend_alphabet=False):
        name = path.basename(file)
        m = self.fsp2lts(file)
        return self.lts2fsm(m, controllable, observable, extend_alphabet=extend_alphabet, name=name)
    
    def fsm2lts(self, obj, alphabet=None, name=None, extend_alphabet=False):
        tmp = f"tmp/{name}.fsm" if name != None else f"tmp/tmp.{random() * 1000_000}.fsm"
        d.write_fsm(tmp, obj)
        m = StateMachine.from_fsm(tmp, alphabet)
        if extend_alphabet:
            m = m.extend_alphabet(self.alphabet)
        return m
    
    def fsm2fsp(self, obj, alphabet=None, name=None):
        m = self.fsm2lts(obj, alphabet, name)
        tmp = f"tmp/{name}.json" if name != None else f"tmp/tmp.{random() * 1000_000}.json"
        m.to_json(tmp)
        lts = subprocess.check_output([
            "java",
            "-jar",
            path.join(this_file, "./bin/ltsa-helper.jar"),
            "convert",
            "--json",
            tmp,
        ], text=True)
        return lts
    
    def fsp2lts(self, file):
        if file in self.fsp_cache:
            return self.fsp_cache[file]

        print(f"Read {file}...")
        name = path.basename(file)
        tmp_json = f"tmp/{name}.json"
        with open(tmp_json, "w") as f:
            subprocess.run([
                "java",
                "-jar",
                path.join(this_file, "./bin/ltsa-helper.jar"),
                "convert",
                "--lts",
                file,
            ], stdout=f)
        self.fsp_cache[file] = StateMachine.from_json(tmp_json)
        return self.fsp_cache[file]
    
    @staticmethod
    def abstract(file, abs_set):
        print("Abstract", file, "by", abs_set)
        name = path.basename(file)
        tmp_json = f"tmp/abs_{name}.json"
        with open(tmp_json, "w") as f:
            subprocess.run([
                "java",
                "-jar",
                path.join(this_file, "./bin/ltsa-helper.jar"),
                "abstract",
                "-m",
                file,
                "-f",
                "json",
                *abs_set
            ], stdout=f)
        return tmp_json
