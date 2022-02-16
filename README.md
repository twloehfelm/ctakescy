FastAPI app to allow spaCy pipeline components to update cTAKES CAS

No external resources are required to use this app.

There is a single endpoint: /ctakescy/process
  POST Request:
    Three parameters:
      - types: List[str] of ctakes types to modify
          Example:
          [
            "org.apache.ctakes.typesystem.type.textsem.DiseaseDisorderMention", 
            "org.apache.ctakes.typesystem.type.textsem.SignSymptomMention"
          ]
      - negation_algorithm: string from {negex, context}
      - negation_only: boolean
        - Only applies to context for now.
          - If true, only polarity is updated.
          - If false, polarity, historyOf, subject, uncertainty, conditional are updated.
    Two Files in the request body:
      - typesystem: The cTAKES typesystem file (.xml)
      - cas: The cTAKES CAS file (.xml)
  Response:
    - The updated CAS file (.xml)
