import json, os, logging, csv
from singletonmixin import Singleton
from compound import Compound
import numpy as np

DEFAULT_CACHE_FNAME = '../cache/compounds.json'
KEGG_ADDITIONS_TSV_FNAME = '../data/kegg_additions.tsv'

class CompoundEncoder(json.JSONEncoder):
    def default(self, obj):
        if (isinstance(obj, Compound)):
            return obj.to_json_dict()
        return json.JSONEncoder.default(self, obj)

class CompoundCacher(Singleton):
    """
        CompoundCacher is a singleton that handles caching of Compound objects
        for the component-contribution package. The Compounds are retrieved by
        their ID (which is the KEGG ID in most cases).
        The first time a Compound is requested, it is obtained from the relevant
        database and a Compound object is created (this takes a while because
        it usually involves internet communication and then invoking the ChemAxon
        plugin for calculating the pKa values for that structure).
        Any further request for the same Compound ID will draw the object from
        the cache. When the method dump() is called, all cached data is written
        to a file that will be loaded in future python sessions.
    """
    def __init__(self, cache_fname=None):
        base_path = os.path.split(os.path.realpath(__file__))[0]
        self.cache_fname = cache_fname
        if self.cache_fname is None:
            self.cache_fname = os.path.join(base_path, DEFAULT_CACHE_FNAME)
        self.additions_fname = os.path.join(base_path, KEGG_ADDITIONS_TSV_FNAME)
        self.need_to_update_cache_file = False
        self.load()
        self.get_kegg_additions()
        self.dump()
    
    def load(self):
        # parse the JSON cache file and store in a dictionary 'compound_dict'
        self.compound_dict = {}
        self.compound_ids = []
        if os.path.exists(self.cache_fname):
            for d in json.load(open(self.cache_fname, 'r')):
                self.compound_ids.append(d['id'])
                self.compound_dict[d['id']] = Compound.from_json_dict(d)

    def dump(self):
        if self.need_to_update_cache_file:
            fp = open(self.cache_fname, 'w')
            data = sorted(self.compound_dict.values(), key=lambda d:d.compound_id)
            json.dump(data, fp, cls=CompoundEncoder, 
                      sort_keys=True, indent=4,  separators=(',', ': '))
            fp.close()
            self.need_to_update_cache_file = False
        
    def get_kegg_additions(self):
        # fields are: name, cid, inchi
        for row in csv.DictReader(open(self.additions_fname, 'r'), delimiter='\t'):
            cid = int(row['cid'])
            compound_id = 'C%05d' % cid
            inchi = row['inchi']
            # if the compound_id is not in the cache, or its InChI has changed,
            # recalculate the Compound() and add/replace in cache
            if (compound_id not in self.compound_dict) or \
               (inchi != self.compound_dict[compound_id].inchi):
                logging.info('Calculating pKa for additional compound: ' + compound_id)
                pKas, majorMSpH7, nHs, zs = Compound.get_species_pka(inchi)
                comp = Compound('KEGG', compound_id, inchi,
                                pKas, majorMSpH7, nHs, zs)
                self.compound_dict[comp.compound_id] = comp
                self.need_to_update_cache_file = True

    def get_kegg_compound(self, cid):
        compound_id = 'C%05d' % cid
        if compound_id in self.compound_dict:
            return self.compound_dict[compound_id]
        else:
            logging.info('Downloading structure and calculating pKa for: ' + compound_id)
            comp = Compound.from_kegg(cid)
            self.compound_dict[comp.compound_id] = comp
            self.need_to_update_cache_file = True
            return comp
            
    def get_kegg_ematrix(self, cids):
        # gather the "atom bags" of all compounds in a list 'atom_bag_list'
        elements = set()
        atom_bag_list = []
        for cid in cids:
            comp = self.get_kegg_compound(cid)
            atom_bag = comp.get_atom_bag_with_electrons()
            if atom_bag is not None:
                elements = elements.union(atom_bag.keys())
            atom_bag_list.append(atom_bag)
        elements.discard('H') # no need to balance H atoms (balancing electrons is sufficient)
        elements = sorted(elements)
        
        # create the elemental matrix, where each row is a compound and each
        # column is an element (or e-)
        Ematrix = np.matrix(np.zeros((len(atom_bag_list), len(elements))))
        for i, atom_bag in enumerate(atom_bag_list):
            if atom_bag is None:
                Ematrix[i, :] = np.nan
            else:
                for j, elem in enumerate(elements):
                    Ematrix[i, j] = atom_bag.get(elem, 0)
        return elements, Ematrix
        
if __name__ == '__main__':
    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)
    ccache = CompoundCacher.getInstance()
    ccache.get_kegg_compound(125)
    ccache.dump()
