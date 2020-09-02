
def missing_blocks(L, start, end): 
    if end - start <= 1:  
        if L[end] - L[start] > 1: 
            yield from range(L[start] + 1, L[end]) 
        return   
    index = start + (end - start) // 2   
    # is the lower half consecutive? 
    consecutive_low =  L[index] == L[start] + (index - start) 
    if not consecutive_low: 
        yield from missing_elements(L, start, index)   
    # is the upper part consecutive? 
    consecutive_high =  L[index] == L[end] - (end - index) 
    if not consecutive_high: 
        yield from missing_elements(L, index, end) 
