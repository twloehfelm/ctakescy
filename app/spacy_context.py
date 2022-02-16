from fastapi import FastAPI, UploadFile, File, Query, Response
from pydantic import BaseModel

from typing import List, Optional
from enum import Enum

from cassis import *
from spacy.tokens import Doc
import spacy
from medspacy.visualization import visualize_ent, visualize_dep
from spacy.tokens import Span
from spacy.language import Language
from spacy.util import filter_spans
from typing import List
from negspacy.negation import Negex
from negspacy.termsets import termset
import textdescriptives as td

from contextvars import ContextVar

Doc.set_extension("ctakes_typesystem", default=None)
Doc.set_extension("ctakes_cas", default=None)
Span.set_extension("ctakes_polarity", default=None)
Span.set_extension("ctakes_begin", default=None)
Span.set_extension("ctakes_end", default=None)
Span.set_extension("ctakes_xmiID",default=None)

# Placeholders for Cassis CAS and TypeSystem objects
cas_contextvar = ContextVar('', default=None)
ts_contextvar = ContextVar('', default=None)

class NegationAlgorithm(str, Enum):
  negex = "negex"
  context = "context"

@spacy.registry.misc("get_cas")
def get_cas():
  return cas_contextvar.get()

@spacy.registry.misc("get_ts")
def get_ts():
  return ts_contextvar.get()

@Language.factory("ctakes_struc", default_config={"cas": Cas, "typesystem": TypeSystem})
def initialize_ctakes_struc(nlp: Language, name: str, cas: Cas, typesystem: TypeSystem):
  return CtakesStruc(nlp, cas, typesystem)

class CtakesStruc:
  def __init__(self, nlp: Language, cas: Cas, typesystem: TypeSystem):
    self.cas = cas
    self.typesystem = typesystem
        
  def __call__(self, doc: Doc) -> Doc:
    doc._.ctakes_typesystem = self.typesystem
    doc._.ctakes_cas = self.cas
    return doc

@Language.factory("ctakes_sentences")
def create_ctakes_sentences(nlp: Language, name: str):
  return CtakesSentences(nlp)

class CtakesSentences:
  def __init__(self, nlp: Language):
    return

  def __call__(self, doc: Doc) -> Doc:
    cas = doc._.ctakes_cas
    sentences = cas.select("org.apache.ctakes.typesystem.type.textspan.Sentence")
    sentence_starts = [sentence.begin for sentence in sentences]

    for i, token in enumerate(doc):
      if token.idx in sentence_starts:
        doc[i].sent_start = True
    return doc

@Language.factory("ctakes_annotations")
def create_ctakes_annotations(
  nlp: Language, 
  name: str, 
  types: List[str] = [],
  ):
  return CtakesAnnotations(nlp, types)

class CtakesAnnotations:
  def __init__(self, nlp: Language, types: List[str]):
    self.types = types

  def __call__(self, doc: Doc) -> Doc:
    cas = doc._.ctakes_cas
    cas_tokens = []
    original_ents = list(doc.ents)
    for t in self.types:
      cas_tokens = cas.select(t)
      new_ents = []
      for token in cas_tokens:
        start = token.begin
        end = token.end
        span = doc.char_span(start, end)
        if span is not None:
          new_ents.append((span.start, span.end, span.text, token.polarity == -1, token.begin, token.end, token.xmiID))
        for ent in new_ents:
          start, end, name, polarity, ctakes_begin, ctakes_end, ctakes_xmiID = ent
          per_ent = Span(doc, start, end, label=t.split('.')[-1].replace('Mention',''))
          per_ent._.ctakes_polarity = polarity
          per_ent._.ctakes_begin = ctakes_begin
          per_ent._.ctakes_end = ctakes_end
          per_ent._.ctakes_xmiID = ctakes_xmiID
          original_ents.append(per_ent)
        
    filtered = filter_spans(original_ents)
    doc.ents = filtered   
    return doc

app = FastAPI()

@app.post("/ctakecy/process")
async def process(
  typesystem: UploadFile = File(...), 
  cas_file: UploadFile = File(...), 
  types: Optional[List[str]] = Query(None),
  negation_algorithm: NegationAlgorithm = NegationAlgorithm.negex,
  negation_only: bool = True
  ):
  ts_contextvar.set(load_typesystem(typesystem.file))
  ts = ts_contextvar.get()
  cas_contextvar.set(load_cas_from_xmi(cas_file.file, typesystem=ts))
  cas = cas_contextvar.get()
  types: types
  
  # Initialize a blank English language model - no pipeline steps
  nlp = spacy.blank("en")

  # Initialize the cTAKES properties - set doc._.ctakes_cas and *.ctakes_typesystem properties to the Cas and TypeSystem objects from Cassis
  nlp.add_pipe("ctakes_struc", config={"cas": {"@misc": "get_cas"}, "typesystem": {"@misc": "get_ts"}})

  # Define spacy sentences based on cTAKES annotation boundaries
  nlp.add_pipe("ctakes_sentences")

  # Add cTAKES annotations from the specified type list as spaCy spans
  nlp.add_pipe("ctakes_annotations", config={"types": types})

  # medspacy_context - sets ent._.is_negated, is_hypothetical, is_conditional, is_historical, 
  nlp.add_pipe("medspacy_context")

  # negex - sets ent._.negex
  # termsets options are: "en", "en_clinical" (default), "en_clinical_sensitive"
  negex_ts = termset("en_clinical_sensitive")
  nlp.add_pipe("negex", config={
    "neg_termset":negex_ts.get_patterns()
  })

  # Readability metrics from textdescriptives package
  nlp.add_pipe('descriptive_stats')
  nlp.add_pipe('readability')
  doc = nlp(cas.sofa_string)

  for t in types:
    cas_tokens = cas.select(t)
    token_label = t.split('.')[-1].replace('Mention','')
    ents = [ent for ent in doc.ents if ent.label_ == token_label]
    for ent in ents:
      for token in cas_tokens:
        if token.xmiID == ent._.ctakes_xmiID:
          if negation_algorithm == NegationAlgorithm.context:
            token.polarity = -1 if ent._.is_negated else 1
            if not negation_only:
              token.uncertainty = 1 if ent._.is_uncertain else 0
              token.conditional = ent._.is_hypothetical
              token.historyOf = 1 if ent._.is_historical else 0
              token.subject = "family" if ent._.is_family else "patient"
          elif negation_algorithm == NegationAlgorithm.negex:
            token.polarity = -1 if ent._.negex else 1
        else:
          continue

  return Response(content=cas.to_xmi(), media_type="application/xml")

