"""
Feature calculations.
"""
import logging
import types
import numpy as np
import multiprocessing
from typing import Iterable, Union

logger = logging.getLogger(__name__)


def _featurize_complex(featurizer, mol_pdb_file, protein_pdb_file, log_message):
  logging.info(log_message)
  return featurizer._featurize_complex(mol_pdb_file, protein_pdb_file)


class Featurizer(object):
  """Abstract class for calculating a set of features for a datapoint.

  This class is abstract and cannot be invoked directly. You'll
  likely only interact with this class if you're a developer. In
  that case, you might want to make a child class which
  implements the `_featurize` method for calculating features for
  a single datapoints if you'd like to make a featurizer for a
  new datatype.
  """

  def featurize(self, datapoints, log_every_n=1000):
    """Calculate features for datapoints.

    Parameters
    ----------
    datapoints: iterable 
       A sequence of objects that you'd like to featurize. Subclassses of
       `Featurizer` should instantiate the `_featurize` method that featurizes
       objects in the sequence.

    Returns
    -------
    A numpy array containing a featurized representation of `datapoints`.
    """
    datapoints = list(datapoints)
    features = []
    for i, point in enumerate(datapoints):
      if i % log_every_n == 0:
        logger.info("Featurizing datapoint %i" % i)
      try:
        features.append(self._featurize(point))
      except:
        logger.warning(
            "Failed to featurize datapoint %d. Appending empty array")
        features.append(np.array([]))

    features = np.asarray(features)
    return features

  def __call__(self, datapoints):
    """Calculate features for datapoints.

    Parameters
    ----------
    datapoints: object 
       Any blob of data you like. Subclasss should instantiate
       this. 
    """
    return self.featurize(datapoints)


class ComplexFeaturizer(object):
  """"
  Abstract class for calculating features for mol/protein complexes.
  """

  def featurize_complexes(self, mol_files, protein_pdbs):
    """
    Calculate features for mol/protein complexes.

    Parameters
    ----------
    mols: list
      List of PDB filenames for molecules.
    protein_pdbs: list
      List of PDB filenames for proteins.

    Returns
    -------
    features: np.array
      Array of features
    failures: list
      Indices of complexes that failed to featurize.
    """
    pool = multiprocessing.Pool()
    results = []
    for i, (mol_file, protein_pdb) in enumerate(zip(mol_files, protein_pdbs)):
      log_message = "Featurizing %d / %d" % (i, len(mol_files))
      results.append(
          pool.apply_async(_featurize_complex,
                           (self, mol_file, protein_pdb, log_message)))
    pool.close()
    features = []
    failures = []
    for ind, result in enumerate(results):
      new_features = result.get()
      # Handle loading failures which return None
      if new_features is not None:
        features.append(new_features)
      else:
        failures.append(ind)
    features = np.asarray(features)
    return features, failures

  def _featurize_complex(self, mol_pdb, complex_pdb):
    """
    Calculate features for single mol/protein complex.

    Parameters
    ----------
    mol_pdb: list
      Should be a list of lines of the PDB file.
    complex_pdb: list
      Should be a list of lines of the PDB file.
    """
    raise NotImplementedError('Featurizer is not defined.')


class MolecularFeaturizer(Featurizer):
  """Abstract class for calculating a set of features for a
  molecule.

  The defining feature of a `MolecularFeaturizer` is that it
  uses SMILES strings and RDKIT molecule objects to represent
  small molecules. All other featurizers which are subclasses of
  this class should plan to process input which comes as smiles
  strings or RDKIT molecules. 

  Child classes need to implement the _featurize method for
  calculating features for a single molecule.

  Note
  ----
  In general, subclasses of this class will require RDKit to be installed.
  """

  def featurize(self, molecules, log_every_n=1000):
    """Calculate features for molecules.

    Parameters
    ----------
    molecules: RDKit Mol / SMILES string /iterable
        RDKit Mol, or SMILES string or iterable sequence of RDKit mols/SMILES
        strings.

    Returns
    -------
    A numpy array containing a featurized representation of
    `datapoints`.
    """
    try:
      from rdkit import Chem
      from rdkit.Chem.rdchem import Mol
    except ModuleNotFoundError:
      raise ValueError("This class requires RDKit to be installed.")
    # Special case handling of single molecule
    if isinstance(molecules, str) or isinstance(molecules, Mol):
      molecules = [molecules]
    else:
      # Convert iterables to list
      molecules = list(molecules)
    features = []
    for i, mol in enumerate(molecules):
      if i % log_every_n == 0:
        logger.info("Featurizing datapoint %i" % i)
      try:
        # Process only case of SMILES strings.
        if isinstance(mol, str):
          # mol must be a SMILES string so parse
          mol = Chem.MolFromSmiles(mol)
        features.append(self._featurize(mol))
      except:
        logger.warning(
            "Failed to featurize datapoint %d. Appending empty array")
        features.append(np.array([]))

    features = np.asarray(features)
    return features

  def _featurize(self, mol):
    """
    Calculate features for a single molecule.

    Parameters
    ----------
    mol : RDKit Mol
        Molecule.
    """
    raise NotImplementedError('Featurizer is not defined.')

  def __call__(self, molecules):
    """
    Calculate features for molecules.

    Parameters
    ----------
    molecules: iterable
        An iterable yielding RDKit Mol objects or SMILES strings.
    """
    return self.featurize(molecules)


class StructureFeaturizer(Featurizer):
  """
  Abstract class for calculating a set of features for an
  inorganic crystal structure.

  The defining feature of a `StructureFeaturizer` is that it
  operates on 3D crystal structures with periodic boundary conditions. 
  Inorganic crystal structures are represented by Pymatgen structure
  objects. Featurizers for inorganic crystal structures that are subclasses of
  this class should plan to process input which comes as pymatgen
  structure objects. 

  Child classes need to implement the _featurize method for
  calculating features for a single crystal.

  Notes
  -----
  Some subclasses of this class will require pymatgen and matminer to be
  installed.

  """

  def featurize(self, structures: Iterable[dict],
                log_every_n: int = 1000) -> np.ndarray:
    """Calculate features for crystal structures.

    Parameters
    ----------
    structures: Iterable[dict]
      Iterable sequence of pymatgen structure dictionaries.
      Json-serializable dictionary representation of pymatgen.core.structure
      https://pymatgen.org/pymatgen.core.structure.html
    log_every_n: int, default 1000
      Logging messages reported every `log_every_n` samples.

    Returns
    -------
    features: np.ndarray
      A numpy array containing a featurized representation of
      `structures`.

    """

    # Special case handling of single crystal structure
    if not isinstance(structures, Iterable):
      structures = [structures]
    else:
      # Convert iterables to list
      structures = list(structures)

    try:
      from pymatgen import Structure
    except ModuleNotFoundError:
      raise ValueError("This class requires pymatgen to be installed.")

    features = []
    for idx, structure in enumerate(structures):
      if idx % log_every_n == 0:
        logger.info("Featurizing datapoint %i" % idx)
      try:
        s = Structure.from_dict(structure)
        features.append(self._featurize(s))
      except:
        logger.warning(
            "Failed to featurize datapoint %i. Appending empty array" % idx)
        features.append(np.array([]))

    features = np.asarray(features)
    return features

  def _featurize(self, structure: "pymatgen.Structure"):
    """Calculate features for a single crystal structure.

    Parameters
    ----------
    structure: pymatgen.Structure object
      Structure object with 3D coordinates and periodic lattice.

    """

    raise NotImplementedError('Featurizer is not defined.')

  def __call__(self, structures: Iterable[dict]):
    """Calculate features for crystal structures.

    Parameters
    ----------
    structures: Iterable[dict]
      An iterable of crystal structure dictionaries.

    """

    return self.featurize(structures)


class CompositionFeaturizer(Featurizer):
  """
  Abstract class for calculating a set of features for an
  inorganic crystal composition.

  The defining feature of a `CompositionFeaturizer` is that it
  operates on 3D crystal chemical compositions. 
  Inorganic crystal compositions are represented by Pymatgen composition
  objects. Featurizers for inorganic crystal compositions that are 
  subclasses of this class should plan to process input which comes as
  Pymatgen composition objects. 

  Child classes need to implement the _featurize method for
  calculating features for a single composition.

  Notes
  -----
  Some subclasses of this class will require pymatgen and matminer to be
  installed.

  """

  def featurize(self, compositions: Iterable[str],
                log_every_n: int = 1000) -> np.ndarray:
    """Calculate features for crystal compositions.

    Parameters
    ----------
    compositions: Iterable[str]
      Iterable sequence of composition strings, e.g. "MoS2".
    log_every_n: int, default 1000
      Logging messages reported every `log_every_n` samples.

    Returns
    -------
    features: np.ndarray
      A numpy array containing a featurized representation of
      `compositions`.

    """

    # Special case handling of single crystal composition
    if not isinstance(compositions, Iterable):
      compositions = [compositions]
    else:
      # Convert iterables to list
      compositions = list(compositions)

    try:
      from pymatgen import Composition
    except ModuleNotFoundError:
      raise ValueError("This class requires pymatgen to be installed.")

    features = []
    for idx, composition in enumerate(compositions):
      if idx % log_every_n == 0:
        logger.info("Featurizing datapoint %i" % idx)
      try:
        c = Composition(composition)
        features.append(self._featurize(c))
      except:
        logger.warning(
            "Failed to featurize datapoint %i. Appending empty array" % idx)
        features.append(np.array([]))

    features = np.asarray(features)
    return features

  def _featurize(self, composition: "pymatgen.Composition"):
    """Calculate features for a single crystal composition.

    Parameters
    ----------
    composition: pymatgen.Composition object
      Composition object for 3D inorganic crystal.

    """

    raise NotImplementedError('Featurizer is not defined.')

  def __call__(self, compositions: Iterable[str]):
    """Calculate features for crystal compositions.

    Parameters
    ----------
    compositions: Iterable[str]
      An iterable of crystal compositions.

    """

    return self.featurize(compositions)


class UserDefinedFeaturizer(Featurizer):
  """Directs usage of user-computed featurizations."""

  def __init__(self, feature_fields):
    """Creates user-defined-featurizer."""
    self.feature_fields = feature_fields
