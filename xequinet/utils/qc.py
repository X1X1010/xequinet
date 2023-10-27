from typing import Optional, Union
import re
from pathlib import Path

from pyscf import gto
import numpy as np
# import scipy.special
import torch


# Atomic Units
AU = 1.0
Bohr = BOHR = 1.0
Hartree = HARTREE = 1.0

# energy
eV = EV = 27.211386024367243
mHartree = MHARTREE = Hartree * 1000
meV = MEV = eV * 1000
kcal_per_mol = KCAL_PER_MOL = 627.5094738898777  # although not a unit of energy, it is often used to represent energy

# length
Angstrom = ANGSTROM = 0.5291772105638411
# dipole
Debye = DEBYE = 2.5417464157449032
mDebye = MDEBYE = Debye * 1000

PROP_UNIT = None
LEN_UNIT = "Angstrom"

unit_set = {
    "AU", "BOHR", "HARTREE", "EV", "MHARTREE", "MEV", "KCAL_PER_MOL", "ANGSTROM", "DEBYE", "MDEBYE",
}

def eval_unit(unit: str):
    # check if the unit is valid and safe
    split_unit = re.split(r"[+ | \- | * | / | ^ | ( | )]", unit)
    for u in split_unit:
        if u == '':
            continue
        elif u in unit_set:
            continue
        elif u.isdigit():
            continue
        else:
            raise ValueError(f"Invalid unit expression: {u}")
    unit = unit.replace('^', '**')

    return eval(unit)


def unit_conversion(unit_in: Optional[str], unit_out: Optional[str]):
    if unit_in is None or unit_out is None:
        return 1.
    unit_in = unit_in.upper()
    unit_out = unit_out.upper()
    if unit_in == unit_out:
        return 1.
    value_in = eval_unit(unit_in)
    value_out = eval_unit(unit_out)

    return value_out / value_in

def set_default_unit(prop_unit: str, len_unit: str):
    global PROP_UNIT, LEN_UNIT
    PROP_UNIT = prop_unit
    LEN_UNIT = len_unit

def get_default_unit():
    return PROP_UNIT, LEN_UNIT


THIS_FOLDER = Path(__file__).parent
BASIS_FOLDER = THIS_FOLDER / "basis"
PRE_FOLDER = THIS_FOLDER / "pre_computed"

# periodic table of elements
# atomic numbers to element symbols
ELEMENTS_LIST = ['d',
  'H' ,                                                                                                 'He',
  'Li', 'Be',                                                             'B' , 'C' , 'N' , 'O' , 'F' , 'Ne',
  'Na', 'Mg',                                                             'Al', 'Si', 'P' , 'S' , 'Cl', 'Ar',
  'K' , 'Ca', 'Sc', 'Ti', 'V' , 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr',
  'Rb', 'Sr', 'Y' , 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn', 'Sb', 'Te', 'I' , 'Xe',
]
# element symbols to atomic numbers
ELEMENTS_DICT = {e: i for i, e in enumerate(ELEMENTS_LIST)}
# ground state multiplicities for each element
ATOM_MULT = [-1,
  2,                                                 1,
  2, 1,                               2, 3, 4, 3, 2, 1,
  2, 1,                               2, 3, 4, 3, 2, 1,
  2, 1, 2, 3, 4, 7, 6, 5, 4, 3, 2, 1, 2, 3, 4, 3, 2, 1,
  2, 1, 2, 3, 6, 7, 6, 5, 4, 1, 2, 1, 2, 3, 4, 3, 2, 1,
]
# atomic masses
ATOM_MASS = torch.Tensor([0.0,
    1.0080, 4.0026, 6.94,   9.0122, 10.81,  12.011, 14.007, 15.999, 18.998, 20.180,
    22.990, 24.305, 26.982, 28.085, 30.974, 32.06,  35.45,  39.95,  39.098, 40.078,
    44.956, 47.867, 50.942, 51.996, 54.938, 55.845, 58.933, 58.693, 63.546, 65.38,
    69.723, 72.630, 74.922, 78.971, 79.904, 83.798, 85.468, 87.62,  88.906, 91.224,
    92.906, 95.95,  98.,    101.07, 102.91, 106.42, 107.87, 112.41, 114.82, 118.71,
    121.76, 127.60, 126.90, 131.29,
])


def gen_int2c1e(embed_basis="gfn2-xtb", aux_basis="aux28"):
    """
    Projection of atomic orbitals onto auxiliary basis.
    """
    int2c1e_dict = {}
    if (BASIS_FOLDER / f"{embed_basis}.dat").exists():
        basis = str(BASIS_FOLDER / f"{embed_basis}.dat")
    else:
        basis = embed_basis
    orbaux = str(BASIS_FOLDER / f"{aux_basis}.dat")
    savefile = PRE_FOLDER / f"{embed_basis}_{aux_basis}.pt"
    aux = gto.M(atom="X 0 0 0", basis={'X': orbaux})
    nao_aux = aux.nao
    ao_loc_nr = aux.ao_loc_nr()[:-1]

    for atom, mult in zip(ELEMENTS_LIST[1:], ATOM_MULT[1:]):
        mol = gto.M(
            atom=f"X 0 0 0; {atom} 0 0 0",
            basis={'X': orbaux, atom: basis},
            spin=mult - 1,
        )
        ovlp = mol.intor("int1e_ovlp")
        projection = ovlp[:nao_aux, nao_aux:]
        embedding = np.linalg.norm(projection, axis=-1) # / projection.shape[-1] 
        int2c1e_dict[atom] = torch.from_numpy(embedding[ao_loc_nr])
    torch.save(int2c1e_dict, savefile)


def gen_atom_sp(atom_ref: str):
    """
    Calculate the shift of the atomic energies for each element.
    """
    atom_sp_dict = {}
    if "xtb" in atom_ref:
        from tblite.interface import Calculator
        m_dict = {"gfn2-xtb": "GFN2-xTB", "gfn1-xtb": "GFN1-xTB", "ipea1-xtb": "IPEA1-xTB"}
        for at_no, mult in enumerate(ATOM_MULT, start=1):
            calc = Calculator(
                method=m_dict[atom_ref],
                positions=np.array([[0.0, 0.0, 0.0]]),
                numbers=np.array([at_no]),
            )
            print(f"Calculating single point of atom {atom}")
            energy = calc.singlepoint().get("energy")
            atom_sp_dict[ELEMENTS_LIST[at_no]] = energy
    else:
        from pyscf import dft, scf, cc, dh
        method, basis = atom_ref.split("/")
        if "def2" in basis:
            ecp = basis
        elif "cc-pv" in basis:
            ecp = basis + "-pp"
        else:
            ecp = None
        for atom, mult in zip(ELEMENTS_LIST[1:], ATOM_MULT[1:]):
            try:
                mol = gto.Mole(atom=f"{atom} 0 0 0", basis=basis, spin=mult - 1)
                if ecp is not None:
                    mol.ecp = ecp
                mol.build()
            except:
                print(f"Unsupported atom {atom} for basis {basis}")
                continue
            print(f"Calculating single point of atom {atom}")
            if "xyg" in method or "xdh" in method:
                mf = dh.DH(mol, xc=method).set(max_cycle=150).build_scf().run()
                if not mf.converged:
                    continue
                energy = mf.e_tot
            elif "cc" in method:
                mf = scf.HF(mol).set(max_cycle=150).run()
                mycc = cc.CCSD(mf).set(max_cycle=150).run()
                if not mycc.converged:
                    continue
                if method == "ccsd":
                    energy = mycc.e_tot
                elif method == "ccsd(t)":
                    energy = mycc.e_tot + mycc.ccsd_t()
                else:
                    raise ValueError(f"Unsupported method: {method}")
            else:
                mf = dft.KS(mol, xc=method).set(max_cycle=150).build().run()
                if not mf.converged:
                    continue
                energy = mf.e_tot
            atom_sp_dict[atom] = energy
    torch.save(atom_sp_dict, PRE_FOLDER / f"{method}_{basis}_sp.pt")


def get_embedding_tensor(embed_basis="gfn2-xtb", aux_basis="aux28") -> torch.Tensor:
    """
    Get embedding of atoms in a basis.

    Args:
        `embed_basis`: name of the basis
        `aux_basis`: name of the auxiliary basis
    Returns:
        a tensor of shape ``(n_atoms, n_aux)``
    """
    if not (PRE_FOLDER / f"{embed_basis}_{aux_basis}.pt").exists():
        gen_int2c1e(embed_basis, aux_basis)
    embed_dict = torch.load(PRE_FOLDER / f"{embed_basis}_{aux_basis}.pt")
    embed_tenor = torch.stack([embed_dict[atom] for atom in ELEMENTS_LIST[1:]])
    embed_tenor = torch.cat([torch.zeros(1, embed_tenor.shape[-1]), embed_tenor])
    return embed_tenor.to(torch.get_default_dtype())


def get_atomic_energy(atom_ref: Union[str, dict] = None) -> torch.Tensor:
    """
    Get the shift of the atomic energies for each element.

    Args:
        `atom_ref`: type of element shifts
    Returns:
        a tensor of shape ``(n_atoms,)``
    """
    if atom_ref is None:
        return torch.zeros(len(ELEMENTS_LIST), dtype=torch.float64)
    elif isinstance(atom_ref, dict):
        atomic_energy = torch.zeros(len(ELEMENTS_LIST), dtype=torch.float64)
        at_no = list(atom_ref.keys())
        if isinstance(at_no[0], str):
            at_no = [ELEMENTS_DICT[atom] for atom in at_no]
        atomic_energy[at_no] = torch.DoubleTensor(list(atom_ref.values()))
    else:
        atom_ref = atom_ref.lower()
        if not (PRE_FOLDER / f"{atom_ref.replace('/', '_')}_sp.pt").exists():
            gen_atom_sp(atom_ref)
        atom_sp_dict = torch.load(PRE_FOLDER / f"{atom_ref.replace('/', '_')}_sp.pt")
        atomic_energy = torch.zeros(len(ELEMENTS_LIST), dtype=torch.float64)
        for atom, energy in atom_sp_dict.items():
            atomic_energy[ELEMENTS_DICT[atom]] = energy
    return atomic_energy * unit_conversion("Hartree", PROP_UNIT)


# def calc_cgto_norm(cgto: list):
#     """cgto: [l, [exp1, coeff1], [exp2, coeff2], ...]"""
#     intor = 0.
#     l = cgto[0]
#     for exp1, coeff1 in cgto[1:]:
#         for exp2, coeff2 in cgto[1:]:
#             intor += coeff1 * coeff2 * scipy.special.gamma(l + 0.5) / (2 * (exp1 + exp2)**(l + 0.5))
#     return 1 / np.sqrt(intor)


def get_centroid(at_no: torch.Tensor, coords: torch.Tensor):
    """Calculate the centroid of a molecule."""
    assert at_no.shape[0] == coords.shape[0]
    masses = ATOM_MASS[at_no].unsqueeze(-1)
    centroid = torch.sum(masses * coords, dim=0) / torch.sum(masses)
    return centroid


if __name__ == "__main__":
    gen_atom_sp("pbe/def2-svp")